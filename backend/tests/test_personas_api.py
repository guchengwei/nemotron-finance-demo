def test_filters_endpoint_returns_total_count(client):
  response = client.get('/api/personas/filters')

  assert response.status_code == 200
  payload = response.json()
  assert 'total_count' in payload
  assert payload['total_count'] > 0


def test_sample_endpoint_returns_total_matching_and_sampled_personas(client):
  response = client.get('/api/personas/sample', params={'count': 3})

  assert response.status_code == 200
  payload = response.json()
  assert 'total_matching' in payload
  assert 'sampled' in payload
  assert len(payload['sampled']) <= 3


def test_sample_endpoint_honors_filters(client):
  response = client.get('/api/personas/sample', params={'sex': '男', 'count': 8})

  assert response.status_code == 200
  payload = response.json()
  assert payload['sampled']
  assert all(persona['sex'] == '男' for persona in payload['sampled'])


def test_count_endpoint_returns_total_matching_without_sample_payload(client):
  response = client.get('/api/personas/count')

  assert response.status_code == 200
  payload = response.json()
  assert payload['total_matching'] == 4
  assert 'sampled' not in payload


def test_count_endpoint_honors_combined_filters(client):
  response = client.get(
    '/api/personas/count',
    params={'region': '関東', 'age_min': 30, 'age_max': 50},
  )

  assert response.status_code == 200
  assert response.json() == {'total_matching': 2}


def test_count_endpoint_returns_zero_when_no_match(client):
  response = client.get(
    '/api/personas/count',
    params={'region': '関西', 'financial_literacy': '初心者'},
  )

  assert response.status_code == 200
  assert response.json() == {'total_matching': 0}
