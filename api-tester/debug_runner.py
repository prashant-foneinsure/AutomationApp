from app.services import runner, variables
from app.repositories import variables as variables_repo

# Simulate what run_group does for the Login test
curl = 'curl -X POST "https://dummyjson.com/auth/login" -H "Content-Type: application/json" -H "Accept: application/json" -d \'{"username":"emilys","password":"emilyspass","expiresInMins":30}\''
available = variables_repo.as_map(36)
print('Available before:', available)

outcome = runner.run(curl, method_override='', instruction='', token='', username='', password='', available=available, extractors=None)
print('Captured variables:', outcome.get('captured_variables'))
print('Proposed extractors:', outcome.get('suggested_extractors'))