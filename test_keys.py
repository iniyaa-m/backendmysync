import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from app.config.settings import settings

print(f"GROQ KEY loaded: {settings.GROQ_API_KEY[:15]}...")
print(f"HF KEY loaded:   {settings.HUGGINGFACE_API_KEY[:15]}...")

# Test Groq
print("\n[1] Testing Groq API...")
try:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "Reply with just the word OK"}],
        max_tokens=5,
    )
    print(f"    GROQ: WORKING - response: {res.choices[0].message.content.strip()}")
except Exception as e:
    print(f"    GROQ: FAILED - {e}")

# Test HuggingFace
print("\n[2] Testing HuggingFace API...")
try:
    import urllib.request, json
    req = urllib.request.Request(
        "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest",
        data=json.dumps({"inputs": "I feel great today!"}).encode(),
        headers={
            "Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.loads(r.read())
    print(f"    HUGGINGFACE: WORKING - response: {result}")
except Exception as e:
    print(f"    HUGGINGFACE: FAILED - {e}")
