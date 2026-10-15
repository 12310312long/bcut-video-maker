"""Offline semantic-caption and portable-schema regression tests."""
import json,pathlib,tempfile,unittest
import captions,bcut

class Regressions(unittest.TestCase):
 def test_no_orphan_tail(self):
  text='调运粮棉、集中投放、紧缩资金、抓紧税收彼此配合。'
  xs=captions.split(text);self.assertNotIn('合',xs);self.assertTrue(any('彼此配合' in x for x in xs));self.assertEqual(''.join(captions.key(x) for x in xs),captions.key(text))
 def test_subject_stays_with_its_predicate(self):
  xs=captions.split('一枚银元从六百六十元涨到一千八百多元，大米、棉纱也跟着涨。')
  self.assertIn('大米棉纱也跟着涨',xs);self.assertFalse(any(x.endswith('多元大米') for x in xs))
 def test_sentence_boundary(self):
  xs=captions.split('此前已经有在东北组织经济恢复的经验。七月，他来到上海。')
  self.assertFalse(any('经验七月' in x for x in xs));self.assertEqual(xs[-1],'七月他来到上海')
 def test_scientific_symbols(self):
  for text in ['-3.14','3.14','1:2','1：2','20%','m/s','a=-3.14']:
   self.assertEqual(captions.display(text),text.replace('：',':'))
  xs=captions.split('测量结果为-3.14，比例是1:2。');self.assertTrue(any('-3.14' in x for x in xs));self.assertTrue(any('1:2' in x for x in xs))
 def test_explicit_cuts_cannot_lose_content(self):
  with self.assertRaises(AssertionError):captions.split('保护人民的生命财产。',editorial=['保护人民'])
 def test_template_contains_no_old_machine_path(self):
  raw=(bcut.ASSETS/'sanitized-template.bjson').read_text(encoding='utf-8');self.assertNotRegex(raw,r'[A-Za-z]:[/\\]');self.assertNotIn('模板字幕',raw)
 def test_template_minimal_types_present(self):
  t=bcut.read(bcut.ASSETS/'sanitized-template.bjson')['timelineWidget']['timeline']
  self.assertTrue(any(x['clips'] for x in t['videoTracks']));self.assertTrue(t['audioTracks'][0]['audioClips']);self.assertTrue(t['captionTracks'][0]['captions'])

if __name__=='__main__':unittest.main(verbosity=2)
