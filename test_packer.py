import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from packer import block, load_chunks, pack


def chunk(key='a',text='fragmento útil',score=.8,source='manual.md',start=1,end=2):
    return {'id':key,'source':source,'text':text,'score':score,'line_start':start,'line_end':end}


def data(*items):
    return {'chunks':list(items)}


class PackerTests(unittest.TestCase):
    def test_exact_budget_includes_citation(self):
        c=chunk()
        text,r=pack(data(c),len(block(c)))
        self.assertEqual(text,block(c))
        self.assertEqual(r['remaining_chars'],0)
        text,r=pack(data(c),len(block(c))-1)
        self.assertEqual(text,'')
        self.assertEqual(r['skipped'][0]['reason'],'over_budget')

    def test_separators_count(self):
        a,b=chunk('a'),chunk('b',text='otra idea')
        exact=len(block(a))+len(block(b))+2
        text,r=pack(data(a,b),exact)
        self.assertEqual(len(text),exact)
        self.assertEqual(r['used_chars'],exact)
        self.assertEqual(len(pack(data(a,b),exact-1)[1]['selected']),1)

    def test_deduplicate_preserves_best_provenance(self):
        a,b=chunk('a',text=' CAFe\u0301  claro ',score=.3),chunk('b',text='café claro',score=.9,source='other.md')
        text,r=pack(data(a,b))
        self.assertEqual([c['id'] for c in r['selected']],['b'])
        self.assertEqual(r['skipped'],[{'id':'a','reason':'duplicate','duplicate_of':'b'}])
        self.assertIn('other.md',text)

    def test_source_cap(self):
        r=pack(data(chunk('a','uno',.9),chunk('b','dos',.8),chunk('c','tres',.7)),per_source=1,mode='score')[1]
        self.assertEqual([c['id'] for c in r['selected']],['a'])
        self.assertEqual(r['source_counts'],{'manual.md':1})
        self.assertTrue(all(s['reason']=='per_source_limit' for s in r['skipped']))

    def test_skip_oversize_then_select_smaller(self):
        a,b=chunk('a','x'*500,.9),chunk('b','short',.5)
        r=pack(data(a,b),len(block(b)),mode='score')[1]
        self.assertEqual([c['id'] for c in r['selected']],['b'])

    def test_density_and_score_have_distinct_behavior(self):
        a,b=chunk('a','x'*300,1),chunk('b','short',.5)
        budget=len(block(a))
        self.assertEqual(pack(data(a,b),budget,mode='score')[1]['selected'][0]['id'],'a')
        self.assertEqual(pack(data(a,b),budget,mode='density')[1]['selected'][0]['id'],'b')

    def test_zero_score_excluded(self):
        text,r=pack(data(chunk(score=0)))
        self.assertEqual(text,'')
        self.assertEqual(r['skipped'][0]['reason'],'zero_score')

    def test_empty_input(self):
        text,r=pack(data())
        self.assertEqual((text,r['input_chunks']),('',0))

    def test_reordering_stable_and_tie_break(self):
        a,b=chunk('a','same'),chunk('b','SAME')
        self.assertEqual(pack(data(a,b)),pack(data(b,a)))
        self.assertEqual(pack(data(a,b))[1]['selected'][0]['id'],'a')

    def test_unicode_count_not_bytes(self):
        c=chunk(text='🌱🌱🌱')
        text,r=pack(data(c),len(block(c)))
        self.assertGreater(len(text.encode('utf-8')),r['used_chars'])

    def test_metadata_does_not_copy_text(self):
        c=chunk(text='PRIVATE_SENTINEL_EXAMPLE')
        text,r=pack(data(c))
        self.assertIn(c['text'],text)
        self.assertNotIn(c['text'],json.dumps(r))
        self.assertEqual(r['selected'][0]['line_end'],2)

    def test_invalid_chunks(self):
        bad=[chunk(score=True),chunk(score=float('nan')),chunk(score=2),chunk(source='line\nbreak'),chunk(start=3,end=2),chunk(text=' '),chunk(key='../bad')]
        for c in bad:
            with self.assertRaises(ValueError):
                pack(data(c))
        with self.assertRaises(ValueError):
            pack(data(chunk(),chunk()))

    def test_argument_limits(self):
        for kwargs in ({'budget':0},{'per_source':0},{'budget':True},{'mode':'unknown'}):
            with self.assertRaises(ValueError):
                pack(data(),**kwargs)

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json'
            p.write_text('{"chunks":[],"chunks":[]}')
            with self.assertRaises(ValueError):
                load_chunks(p)

    def test_cli_exact_export_and_input_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/'input.json'
            p.write_text(json.dumps(data(chunk())))
            cli=[sys.executable,str(Path(__file__).with_name('packer.py')),str(p),'--out-dir',str(root/'build')]
            r=subprocess.run(cli,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)
            context=(root/'build/context.txt').read_text()
            m=json.loads((root/'build/manifest.json').read_text())
            self.assertEqual(len(context),m['used_chars'])
            self.assertFalse(context.endswith('\n'))
            self.assertEqual(subprocess.run(cli+['--budget','1'],capture_output=True).returncode,1)
            p=root/'build/manifest.json'
            original=json.dumps(data(chunk()))
            p.write_text(original)
            cli[2]=str(p)
            self.assertEqual(subprocess.run(cli,capture_output=True).returncode,2)
            self.assertEqual(p.read_text(),original)


if __name__=='__main__':
    unittest.main()
