"""Offline semantic-caption and portable-schema regression tests."""
import json,pathlib,tempfile,unittest
import captions,bcut,studio

class Regressions(unittest.TestCase):
 def test_partial_voice_cache_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);mp=root/'voice.mp3';ev=root/'events.json';mp.write_bytes(b'x'*1200)
   bcut.write(ev,[{'text':'保护人民','offset':0,'duration':100}]);self.assertFalse(studio.voice_complete(mp,ev,'保护人民的生命财产。'))
   bcut.write(ev,[{'text':'保护人民的生命财产','offset':0,'duration':100}]);self.assertTrue(studio.voice_complete(mp,ev,'保护人民的生命财产。'))
   ev.write_text('invalid json',encoding='utf-8');self.assertFalse(studio.voice_complete(mp,ev,'保护人民'))
 def test_measured_audio_windows(self):
  tl={'fps':30,'total_frames':600,'segments':[{'id':'part','start_frame':90,'end_frame':300,'text':'开始行动','chars':[{'time':4.0},{'time':4.1},{'time':4.2},{'time':4.3}]}]}
  self.assertEqual(studio.audio_window({'segment':'part'},tl),(90,300))
  self.assertEqual(studio.audio_window({'segment':'part','cue':'行动','start':-.2,'duration':2},tl),(120,180))
  self.assertEqual(studio.audio_window({'start':2,'end':6},tl),(60,180))
  self.assertEqual(studio.audio_window({'segment':'part','start':1,'end':4},tl),(120,210))
  with self.assertRaises(ValueError):studio.audio_window({'start':19,'duration':2},tl)
  with self.assertRaises(ValueError):studio.audio_window({'segment':'missing'},tl)
 def test_original_speech_captions_and_overlap(self):
  tl={'fps':30,'captions':[],'segments':[{'id':'w','start_frame':60,'end_frame':180,'design':{'source_captions':[{'text':'原声，内容。','start':.5,'end':2}]}}]}
  studio.insert_source_captions(tl);self.assertEqual(tl['captions'],[{'text':'原声内容','start':2.5,'end':4.0,'layer':0}])
  tl['captions']=[{'text':'旁白','start':2,'end':3,'layer':0}]
  with self.assertRaises(ValueError):studio.insert_source_captions(tl)
 def test_music_delivery_default_and_explicit_overrides(self):
  self.assertEqual(studio.delivery_variants({'music':[{'asset':'score'}]}),['配乐版'])
  self.assertEqual(studio.delivery_variants({'variants':['无配乐版']}),['无配乐版'])
  self.assertEqual(studio.delivery_variants({'music':[{'asset':'score'}],'variants':['配乐版','无配乐版']}),['配乐版','无配乐版'])
  for job in [{},{'music':[]},{'variants':['配乐版']},{'variants':['配乐版','无配乐版']}]:
   with self.assertRaises(ValueError):studio.delivery_variants(job)
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
