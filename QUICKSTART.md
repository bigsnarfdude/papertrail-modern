# Quick Start Guide

## 1. Start the System

### Using Docker (Recommended)

```bash
cd papertrail-modern
docker-compose up -d
```

Wait ~10 seconds for services to start, then open: **http://localhost:5000**

### Manual Start

```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start Flask app
cd papertrail-modern
pip install -r requirements.txt
python app.py
```

## 2. Test the API

### Submit a test event

```bash
curl -X POST http://localhost:5000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "user_login",
    "user_id": "alice",
    "system": "production_db",
    "metadata": {"ip": "192.168.1.100"}
  }'
```

### Submit multiple events

```bash
# User login
curl -X POST http://localhost:5000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "user_login", "user_id": "bob", "system": "production_db", "metadata": {"ip": "192.168.1.101"}}'

# API access
curl -X POST http://localhost:5000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "api_access", "user_id": "charlie", "system": "api_gateway", "metadata": {"endpoint": "/api/users"}}'

# Database access
curl -X POST http://localhost:5000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "database_access", "user_id": "alice", "system": "production_db", "metadata": {"query": "SELECT"}}'
```

## 3. Query Compliance Data

### Count distinct users (HyperLogLog)

```bash
# Last hour
curl "http://localhost:5000/api/v1/compliance/distinct/users?system=production_db&window=1h"

# Last 24 hours
curl "http://localhost:5000/api/v1/compliance/distinct/users?system=production_db&window=1d"
```

### Check if user accessed system (Bloom Filter)

```bash
curl "http://localhost:5000/api/v1/compliance/activity/check?user_id=alice&system=production_db&window=1d"
```

### Get top active users

```bash
curl "http://localhost:5000/api/v1/compliance/top/active_users?system=production_db&k=10&window=1h"
```

### Get metrics summary

```bash
curl "http://localhost:5000/api/v1/compliance/summary/production_db"
```

## 4. Use the Dashboard

1. Open **http://localhost:5000** in browser
2. Click "Send Test Event" to generate test data
3. Watch real-time event stream update
4. Try the activity checker with user ID "alice" and system "production_db"
5. View top active users and IPs

## 5. Load Testing

Generate 1000 events:

```bash
for i in {1..1000}; do
  curl -X POST http://localhost:5000/api/v1/events \
    -H "Content-Type: application/json" \
    -d "{
      \"event_type\": \"user_login\",
      \"user_id\": \"user_$((RANDOM % 100))\",
      \"system\": \"production_db\",
      \"metadata\": {\"ip\": \"192.168.1.$((RANDOM % 255))\"}
    }" &
done
wait
```

Then query:

```bash
# Should show ~100 unique users
curl "http://localhost:5000/api/v1/compliance/distinct/users?system=production_db&window=1h"

# Should show top active users
curl "http://localhost:5000/api/v1/compliance/top/active_users?system=production_db&k=10"
```

## 6. Run Tests

```bash
cd papertrail-modern
pytest tests/ -v
```

## 7. Stop the System

```bash
# Docker
docker-compose down

# Manual (Ctrl+C in each terminal)
```

## Common Issues

### Port already in use
```bash
# Check what's using port 5000
lsof -i :5000

# Change port in .env
PORT=8080
```

### Redis connection failed
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Check Redis host in .env
REDIS_HOST=localhost  # or 'redis' for Docker
```

### No data showing in dashboard
1. Submit some test events first
2. Wait a few seconds for processing
3. Click "Refresh" button
4. Check browser console for errors

## Next Steps

- Read the full [README.md](README.md) for architecture details
- Check [API documentation](#) at http://localhost:5000/api
- Explore probabilistic data structures in `app/core/sketches/`
- Customize time windows in `.env`
- Integrate with your logging system
