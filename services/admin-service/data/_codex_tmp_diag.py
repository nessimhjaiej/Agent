from pathlib import Path
import sys
for name in list(sys.modules):
    if name == 'app' or name.startswith('app.'):
        del sys.modules[name]
service_root = Path('services/admin-service').resolve()
if str(service_root) in sys.path:
    sys.path.remove(str(service_root))
sys.path.insert(0, str(service_root))
from app.config import Settings
from app.graph import IntentClassifier, _plan_mutation, _plan_request
from app.tools import AdminToolbox

settings = Settings(openai_key='')
message = 'change the reranking strategy to cross-encoder'
classifier = IntentClassifier(settings)
print('CLASSIFY', classifier.classify(message))
toolbox = AdminToolbox(settings)
try:
    print('SCOPE', toolbox.resolve_config_scope(message))
except Exception as exc:
    print('SCOPE_ERROR', exc)
print('PLAN_MUTATION', _plan_mutation(message, toolbox))
print('PLAN_REQUEST_MUTATE', _plan_request(message, 'mutate', toolbox))
print('PLAN_REQUEST_CLASSIFIED', _plan_request(message, classifier.classify(message).category, toolbox))
