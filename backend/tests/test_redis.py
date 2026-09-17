import os
import redis
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL")
if redis_url and redis_url.startswith("redis-cli"):
    # Extract the URL part from the redis-cli command
    redis_url = redis_url.split("-u ")[-1].strip()
    
# Upstash often requires TLS. If the URL is just redis:// but it's an upstash URL, change to rediss://
if redis_url and "upstash.io" in redis_url and redis_url.startswith("redis://"):
    redis_url = redis_url.replace("redis://", "rediss://", 1)

print(f"Connecting to Redis URL: {redis_url[:20]}... (masked for security)")

try:
    # Set ssl_cert_reqs="none" just in case there are local cert issues, 
    # though usually from_url handles rediss:// fine.
    client = redis.Redis.from_url(redis_url, ssl_cert_reqs="none")
    
    # Test ping
    print("Pinging Redis...")
    if client.ping():
        print("[SUCCESS] Successfully connected to Redis! Ping returned True.")
    else:
        print("[ERROR] Failed to ping Redis.")
        
    # Basic set and get test
    print("Testing SET/GET operations...")
    client.set("test_key", "Hello, Redis!")
    val = client.get("test_key")
    if val:
        print(f"[SUCCESS] Successfully retrieved value: {val.decode('utf-8')}")
    else:
        print("[ERROR] Failed to retrieve value.")
        
except Exception as e:
    print(f"[ERROR] Error connecting to Redis: {e}")
