import asyncio
import unittest
import numpy as np
from local_engine import MAX_UTTERANCE, Segmenter, Session, SoundTracker


class SegmentTests(unittest.TestCase):
    def test_silence_never_submits(self):
        s=Segmenter(lambda _:False)
        for _ in range(1000):self.assertEqual(s.push(np.zeros(1600,np.float32)),[])
        self.assertEqual(len(s.pre),2)
        self.assertIsNone(s.finish())

    def test_partial_final_and_duration_cap(self):
        s=Segmenter(lambda a:bool(a[0]))
        jobs=[]
        for _ in range(85):jobs.extend(s.push(np.ones(1600,np.float32)))
        self.assertTrue(any(not j.final for j in jobs))
        self.assertEqual(sum(j.final for j in jobs),1)
        self.assertLessEqual(max(len(j.audio) for j in jobs),MAX_UTTERANCE)
        for _ in range(4):jobs.extend(s.push(np.zeros(1600,np.float32)))
        self.assertTrue(jobs[-1].final)
        self.assertEqual(jobs[-1].segment,1)

    def test_first_partial_arrives_within_half_a_second(self):
        s=Segmenter(lambda a:True)
        first=next(i for i in range(20) if s.push(np.ones(1600,np.float32)))
        self.assertLessEqual((first+1)*0.1,0.5)

    def test_cap_splits_at_quietest_packet_without_losing_audio(self):
        s=Segmenter(lambda a:True)
        jobs=[]
        for i in range(90):
            level=0.01 if i==70 else 1.0
            jobs.extend(s.push(np.full(1600,level,np.float32)))
        final=next(j for j in jobs if j.final)
        self.assertEqual(len(final.audio),71*1600)
        self.assertAlmostEqual(final.end,7.1)
        rest=s.finish()
        self.assertAlmostEqual(rest.start,7.1)
        self.assertEqual(len(final.audio)+len(rest.audio),90*1600)


class SoundTrackerTests(unittest.TestCase):
    def test_hysteresis_reports_start_and_end_once(self):
        t=SoundTracker({'laughter':.3})
        self.assertEqual(t.update({'laughter':.35}),(['laughter'],['laughter'],[]))
        self.assertEqual(t.update({'laughter':.2}),(['laughter'],[],[]))
        self.assertEqual(t.update({'laughter':.1}),([],[],['laughter']))

    def test_recurring_cue_is_not_reannounced_within_cooldown(self):
        t=SoundTracker({'crying':.3})
        starts=[t.update({'crying':.5 if i%3==0 else 0})[1] for i in range(30)]
        announced=[i for i,s in enumerate(starts) if s]
        self.assertEqual(announced,[0,12,24])


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_flush_preserves_independent_final_results(self):
        class Models:
            def infer(self,channel,a):
                if channel=='sound':return {'laughter':.9}
                return {'text':'test'} if channel=='text' else {'tone':{'label':'Uncertain'}}
        events=[]
        async def send(e):events.append(e)
        s=Session(Models(),send,vad=lambda _:True)
        try:
            for _ in range(25):await s.feed(np.ones(1600,np.float32))
            await s.flush()
            final_text=[e for e in events if e['type']=='caption' and e['final']]
            self.assertEqual([e['end'] for e in final_text],[2.5])
            self.assertTrue(any(e['type']=='tone' and e['final'] for e in events))
            sounds=[e for e in events if e['type']=='sound']
            self.assertEqual(len(sounds),1)
            self.assertEqual(sounds[0]['started'],['laughter'])
        finally:await s.close()


if __name__=='__main__':unittest.main()
