import sys
sys.path.insert(0, '/home/Bilirubin/.hermes/hermes-agent')
sys.path.insert(0, '/home/Bilirubin/.hermes/venv/lib/python3.11/site-packages')
from tools.memory_tool import memory_record_observation
import json

rule = (
    "BEHAVIORAL RULE - PROPOSE THEN ACT, NOT ASK THEN WAIT\n\n"
    "Core principle: The user wants to approve proposals, not answer questions.\n\n"
    "WRONG pattern (asking):\n"
    "- 'What name should I give the bot?'\n"
    "- 'Which approach should I use - A or B?'\n"
    "- 'What content do you want to post?'\n\n"
    "RIGHT pattern (proposing):\n"
    "- 'I will create @CareerOdysseyNewsBot. Ready to start?'\n"
    "- 'Plan: 1) create bot, 2) set up channel, 3) daily AI news posts at 9am. OK?'\n"
    "- 'I will use RSS from TechCrunch + AI summary. Proceed or want different source?'\n\n"
    "Rules:\n"
    "1. Make concrete proposals with specific names, approaches, and defaults chosen by you.\n"
    "2. Present the full plan upfront so the user can approve or redirect in one message.\n"
    "3. Use clarify ONLY with multiple-choice proposals (never open-ended questions).\n"
    "4. After approval, execute completely without asking again.\n"
    "5. NEVER say 'you must do X yourself' - find a way to do it (browser, API, CLI, SSH).\n\n"
    "For Telegram bots specifically: use browser automation (Telegram Web + BotFather) "
    "to create bots without requiring the user to do anything manually."
)

result = json.loads(memory_record_observation(
    content=rule,
    collection='obsidian-rules',
    workspace_slug='agent_ops',
    tags=['autonomy', 'behavior', 'clarify', 'rule', 'propose']
))
print(result.get('success'), result.get('id', result.get('error', '')))
