"""Pack pre-ranked RAG chunks into a strict character budget, with provenance."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys
import unicodedata


def normalized(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}: entero entre {low} y {high}')
    return value


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('chunks'), list) or len(data['chunks']) > 500:
        raise ValueError('Se requiere chunks como lista de hasta 500 fragmentos')
    seen, result = set(), []
    for item in data['chunks']:
        if not isinstance(item, dict):
            raise ValueError('Fragmento no válido')
        key, source, text, score = (item.get(k) for k in ('id','source','text','score'))
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key) or key in seen:
            raise ValueError('ID inválido o duplicado')
        if not isinstance(source,str) or not source.strip() or len(source)>200 or any(ord(c)<32 for c in source) or '\u2028' in source or '\u2029' in source:
            raise ValueError('source debe ser texto de una línea, no vacío, de hasta 200 caracteres')
        if not isinstance(text,str) or not text.strip() or len(text)>20000:
            raise ValueError('text debe ser texto no vacío de hasta 20000 caracteres')
        if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1:
            raise ValueError('score debe ser un número finito entre 0 y 1')
        start=integer(item.get('line_start'),1,10000000,'line_start')
        end=integer(item.get('line_end'),start,10000000,'line_end')
        seen.add(key)
        result.append({'id':key,'source':source,'text':text,'score':float(score),'line_start':start,'line_end':end})
    return result


def block(chunk):
    return f'[{chunk["id"]}] {chunk["source"]} (líneas {chunk["line_start"]}-{chunk["line_end"]})\n{chunk["text"]}'


def pack(data, budget=4000, per_source=2, mode='density'):
    integer(budget,1,1000000,'budget')
    integer(per_source,1,50,'per-source')
    if mode not in ('density','score'):
        raise ValueError('mode debe ser density o score')
    chunks=validate(data)
    # Deduplicate first: preserve the highest score, then smallest ID.
    representatives={}
    skipped=[]
    for c in sorted(chunks,key=lambda c:(-c['score'],c['id'])):
        fingerprint=normalized(c['text'])
        if fingerprint in representatives:
            skipped.append({'id':c['id'],'reason':'duplicate','duplicate_of':representatives[fingerprint]['id']})
        else:
            representatives[fingerprint]=c
    candidates=list(representatives.values())
    def priority(c):
        value=c['score']/len(block(c)) if mode=='density' else c['score']
        return (-value,-c['score'],c['id'])
    candidates.sort(key=priority)
    chosen,blocks=[],[]
    counts=Counter()
    used=0
    for c in candidates:
        extra=len(block(c))+(2 if blocks else 0)
        if c['score']==0:
            reason='zero_score'
        elif counts[c['source']]>=per_source:
            reason='per_source_limit'
        elif used+extra>budget:
            reason='over_budget'
        else:
            used+=extra
            counts[c['source']]+=1
            blocks.append(block(c))
            chosen.append({k:c[k] for k in ('id','source','score','line_start','line_end')})
            chosen[-1]['block_chars']=len(block(c))
            continue
        skipped.append({'id':c['id'],'reason':reason})
    context='\n\n'.join(blocks)
    assert len(context)==used and used<=budget
    report={'budget_chars':budget,'used_chars':used,'remaining_chars':budget-used,
            'mode':mode,'per_source_limit':per_source,'input_chunks':len(chunks),
            'selected':chosen,'skipped':sorted(skipped,key=lambda c:c['id']),
            'source_counts':dict(sorted(counts.items())),
            'notice':'Selección heurística sobre puntuaciones suministradas; caracteres no equivalen a tokens ni garantizan relevancia.'}
    return context,report


def unique_object(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:
            raise ValueError('Clave JSON repetida: '+key)
        obj[key]=value
    return obj


def load_chunks(path):
    if path.stat().st_size>2*1024*1024:
        raise ValueError('La entrada supera 2 MiB')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique_object)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('chunks',type=Path)
    parser.add_argument('--budget',type=int,default=4000)
    parser.add_argument('--per-source',type=int,default=2)
    parser.add_argument('--mode',choices=('density','score'),default='density')
    parser.add_argument('--out-dir',type=Path,default=Path('build'))
    args=parser.parse_args(argv)
    try:
        context_path=args.out_dir/'context.txt'
        report_path=args.out_dir/'manifest.json'
        if args.chunks.resolve() in (context_path.resolve(),report_path.resolve()):
            raise ValueError('Las salidas no pueden sobrescribir la entrada')
        context,report=pack(load_chunks(args.chunks),args.budget,args.per_source,args.mode)
        args.out_dir.mkdir(parents=True,exist_ok=True)
        # No extra newline: the file itself obeys the exact character budget.
        context_path.write_text(context,encoding='utf-8',newline='')
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'{len(report["selected"])} seleccionados · {report["used_chars"]}/{args.budget} caracteres · {args.out_dir}')
        return 0 if report['selected'] else 1
    except (ValueError,OSError,RecursionError) as exc:
        print('Error: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
