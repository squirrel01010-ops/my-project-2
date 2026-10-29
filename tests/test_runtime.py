import os
import unittest
from unittest.mock import patch,MagicMock
import run

class Supervisor(unittest.TestCase):
 def test_production_requires_credentials(self):
  with patch.dict(os.environ,{'REQUIRE_DISCORD':'1'},clear=True),patch('run.load_dotenv'):
   with self.assertRaises(SystemExit):run.main()
 def test_child_failure_stops_other_child(self):
  web=MagicMock();web.poll.return_value=1
  bot=MagicMock();bot.poll.return_value=None
  env=dict(DISCORD_TOKEN='test',DISCORD_GUILD_ID='1',PUBLIC_URL='https://example.test',REQUIRE_DISCORD='1')
  with patch.dict(os.environ,env,clear=True),patch('run.load_dotenv'),patch('run.signal.signal'),patch('run.subprocess.Popen',side_effect=[web,bot]):
   self.assertEqual(run.main(),1)
  bot.terminate.assert_called_once();web.wait.assert_called_once();bot.wait.assert_called_once()
 def test_failed_heartbeat_requests_restart(self):
  web=MagicMock();web.poll.return_value=None
  env=dict(PUBLIC_URL='http://localhost:8080')
  with patch.dict(os.environ,env,clear=True),patch('run.load_dotenv'),patch('run.signal.signal'),patch('run.subprocess.Popen',return_value=web),patch('run.time.monotonic',side_effect=[0,181]),patch('runtime_health.check',side_effect=RuntimeError):
   self.assertEqual(run.main(),1)
  web.terminate.assert_called_once()
