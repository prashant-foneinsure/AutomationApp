import os
os.environ["AA_LLM_STUB"] = "1"

from app.services import runner, variables
from app.repositories import variables as variables_repo, tests as tests_repo
from app.modules.api_testing import service

# Check what run_group does
from app.modules.api_testing.schemas import GroupRunRequest

request = GroupRunRequest(instruction="", token="", username="", password="", stop_on_failure=True)
result = service.run_group(36, request)
print('Group run result:')
print(f"  group_id: {result['group_id']}")
print(f"  group_run_id: {result['group_run_id']}")
print(f"  steps: {len(result['steps'])}")
for step in result['steps']:
    print(f"  - {step['name']}: skipped={step.get('skipped')}, captured={step.get('captured')}")
print(f"  variables: {result['variables']}")

# Check variables table after
vars_after = variables_repo.list_for_group(36)
print('\nVariables after group run:')
for v in vars_after:
    print(f"  {v}")