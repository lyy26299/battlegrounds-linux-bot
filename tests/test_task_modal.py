import unittest
from pathlib import Path
from PIL import Image
import numpy as np
from vision import Detector
from core import Phase,Planner

class TaskModalTests(unittest.TestCase):
 def test_actual_daily_task_modal_is_dismissed(self):
  image=np.array(Image.open(Path(__file__).parent/'fixtures/daily-tasks-cloud-game.png').convert('RGB'))
  obs=Detector().observe(image)
  self.assertEqual(obs.phase,Phase.CHOICE)
  action=Planner().next(obs)
  self.assertEqual(action.kind,'click')
  self.assertEqual(action.start,(.5,.76))
  self.assertEqual(action.reason,'关闭任务提示')

 def test_actual_event_task_modal_is_dismissed(self):
  image=np.array(Image.open(Path(__file__).parent/'fixtures/event-tasks-cloud-game.png').convert('RGB'))
  obs=Detector().observe(image)
  self.assertEqual(obs.phase,Phase.CHOICE)
  self.assertEqual(Planner().next(obs).start,(.5,.76))
