# 🖥️ Self-Hosted AI: Complete Guide

## 📖 What is Self-Hosted AI?

### **Simple Explanation:**

**Current Setup (OpenAI API):**
```
Your Server → Internet → OpenAI Servers (GPT-4o-mini) → Internet → Your Server
              ↑
         Pay $0.06 per page
```
- You send image to OpenAI
- They run their AI model
- You pay per API call
- **Cost: Variable** ($0.06 per page = $9 for 158 pages)

---

**Self-Hosted AI:**
```
Your Server → Your GPU Server (Llama 3.2 Vision running 24/7)
              ↑
         Pay $200/month fixed
```
- You run the AI model on your own server
- No internet API calls
- Pay fixed monthly cost
- **Cost: Fixed** ($200/month unlimited extractions)

---

## 🤔 Why Self-Host?

### **Cost Comparison:**

| Approach | Month 1<br>(50 docs) | Month 3<br>(200 docs) | Month 6<br>(500 docs) | Month 12<br>(1000 docs) |
|----------|------------|--------------|--------------|---------------|
| **OpenAI API**<br>(gpt-4o-mini) | $450 | $1,800 | $4,500 | $9,000 |
| **Self-Hosted**<br>(Llama 3.2 Vision) | $200 | $200 | $200 | $200 |
| **Savings** | -$250 ❌ | **+$1,600** ✅ | **+$4,300** ✅ | **+$8,800** ✅ |

**Break-even point:** ~22 documents per month

**After break-even:** Every additional document is FREE (100% margin)

---

## 🧠 What AI Models Can You Self-Host?

### **Top Vision Models for Table Extraction:**

| Model | Size | Quality vs GPT-4o | Speed | Hardware Needed | Commercial Use |
|-------|------|-------------------|-------|-----------------|----------------|
| **Llama 3.2 Vision 11B** | 11GB | 70% | Fast | 1× RTX 4090 | ✅ Free |
| **LLaVA-NeXT 13B** | 13GB | 65% | Fast | 1× RTX 4090 | ✅ Free |
| **CogVLM 17B** | 17GB | 75% | Medium | 1× RTX 4090 | ✅ Free |
| **Phi-3-Vision 4B** | 4GB | 60% | Very Fast | RTX 3060 | ✅ Free (Microsoft) |
| **Qwen2-VL 7B** | 7GB | 68% | Fast | RTX 3090 | ✅ Free |

**All these models are:**
- ✅ Free to download and use
- ✅ Run on your hardware
- ✅ No API costs
- ✅ Commercial-friendly licenses
- ✅ Can extract tables from images

---

## 💰 Total Cost of Ownership

### **Option A: Rent GPU Server** (Easiest)

#### **RunPod (Popular Choice):**

| GPU | VRAM | $/hour | $/month (24/7) | Which models fit |
|-----|------|--------|----------------|------------------|
| RTX 3090 | 24GB | $0.44 | $317 | All models above ✅ |
| RTX 4090 | 24GB | $0.69 | $497 | All models above ✅ |
| A40 | 48GB | $0.79 | $569 | Multiple models at once |

**Recommendation:** RTX 3090 @ $317/month

---

#### **Vast.ai (Cheapest):**

| GPU | VRAM | $/hour | $/month (24/7) | Which models fit |
|-----|------|--------|----------------|------------------|
| RTX 3090 | 24GB | $0.20 | $144 | All models above ✅ |
| RTX 4090 | 24GB | $0.34 | $245 | All models above ✅ |

**Recommendation:** RTX 4090 @ $245/month (best value)

⚠️ **Note:** Vast.ai prices fluctuate (marketplace), but cheaper than RunPod

---

### **Option B: Buy Your Own GPU** (Best Long-term)

| Hardware | Cost | Lifespan | Monthly Cost | Break-even |
|----------|------|----------|--------------|------------|
| RTX 3090 (used) | $800 | 3 years | $22 | Month 4 |
| RTX 4090 (new) | $1,600 | 4 years | $33 | Month 7 |
| Electricity | - | - | $30-50 | - |

**Total monthly (own GPU):** $50-85 (vs $200-500 renting)

**When to buy:**
- If you expect 6+ months of consistent usage
- If you have technical expertise to set up
- If you need full data privacy

---

## 📊 Profitability Analysis

### **Scenario 1: Small Scale (50 docs/month)**

| | OpenAI API | Self-Hosted (Vast.ai) |
|---|---|---|
| **Revenue** | 50 × $20 = $1,000 | 50 × $20 = $1,000 |
| **AI Cost** | 50 × $9 = $450 | $245 (fixed) |
| **Other Costs** | $50 | $50 |
| **Profit** | $500 (50%) | $705 (70%) |
| **Winner** | | ✅ **Self-hosted: +$205/month** |

---

### **Scenario 2: Medium Scale (200 docs/month)**

| | OpenAI API | Self-Hosted (Vast.ai) |
|---|---|---|
| **Revenue** | 200 × $20 = $4,000 | 200 × $20 = $4,000 |
| **AI Cost** | 200 × $9 = $1,800 | $245 (fixed) |
| **Other Costs** | $200 | $200 |
| **Profit** | $2,000 (50%) | $3,555 (89%) |
| **Winner** | | ✅ **Self-hosted: +$1,555/month** |

---

### **Scenario 3: Large Scale (1000 docs/month)**

| | OpenAI API | Self-Hosted (Vast.ai) |
|---|---|---|
| **Revenue** | 1000 × $20 = $20,000 | 1000 × $20 = $20,000 |
| **AI Cost** | 1000 × $9 = $9,000 | $245 (fixed) |
| **Other Costs** | $500 | $500 |
| **Profit** | $10,500 (52%) | $19,255 (96%) |
| **Winner** | | ✅ **Self-hosted: +$8,755/month** |

**Key insight:** The more documents you process, the more self-hosting saves you.

---

## 🛠️ How to Set Up Self-Hosted AI

### **Step-by-Step Implementation:**

---

## **Phase 1: Choose Your Model & Provider** (30 minutes)

### **1.1 Pick a model:**

**Recommendation for beginners:** **Llama 3.2 Vision 11B**
- Best balance of quality/speed/ease
- Meta (Facebook) official model
- Great documentation
- Active community

**Download size:** ~11GB

---

### **1.2 Pick a GPU provider:**

**Recommendation:** **Vast.ai** (cheapest, flexible)

**Alternatives:**
- RunPod (easier UI, more expensive)
- Lambda Labs (stable, premium)
- Your own hardware (advanced)

---

## **Phase 2: Rent GPU Server** (10 minutes)

### **2.1 Sign up for Vast.ai:**

1. Go to https://vast.ai
2. Create account
3. Add payment method ($25 minimum deposit)

---

### **2.2 Search for GPU:**

**Filters:**
- GPU: RTX 4090 or RTX 3090
- RAM: 32GB+
- Storage: 100GB+
- Bandwidth: 100 Mbps+

**Sort by:** Price (lowest first)

**Expected cost:** $0.20-0.40/hour

---

### **2.3 Rent the server:**

```bash
# Click "Rent" on cheapest RTX 4090
# Select "PyTorch" template
# Click "Launch"
```

**You'll get:**
- IP address (e.g., 123.45.67.89)
- SSH port (e.g., 12345)
- Root password

---

## **Phase 3: Install & Run Model** (20 minutes)

### **3.1 Connect to server:**

```bash
# From your local machine
ssh root@123.45.67.89 -p 12345

# Enter password when prompted
```

---

### **3.2 Install dependencies:**

```bash
# Update system
apt update && apt upgrade -y

# Install Python & tools
apt install -y python3-pip git

# Install PyTorch with CUDA
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Install Hugging Face transformers
pip3 install transformers accelerate
```

---

### **3.3 Download Llama 3.2 Vision model:**

```bash
# Create directory
mkdir -p /models
cd /models

# Download model (takes 5-10 minutes)
python3 << 'EOF'
from transformers import AutoModelForVision2Seq, AutoProcessor

model_id = "meta-llama/Llama-3.2-11B-Vision-Instruct"

print("Downloading model (11GB)...")
model = AutoModelForVision2Seq.from_pretrained(
    model_id, 
    device_map="auto",
    torch_dtype="auto"
)

processor = AutoProcessor.from_pretrained(model_id)

print("Model downloaded successfully!")
model.save_pretrained("/models/llama-3.2-vision")
processor.save_pretrained("/models/llama-3.2-vision")
EOF
```

---

### **3.4 Create inference server:**

```bash
# Create server script
cat > /root/vision_server.py << 'EOF'
from transformers import AutoModelForVision2Seq, AutoProcessor
from flask import Flask, request, jsonify
from PIL import Image
import torch
import io
import base64

app = Flask(__name__)

# Load model at startup
print("Loading Llama 3.2 Vision model...")
model = AutoModelForVision2Seq.from_pretrained(
    "/models/llama-3.2-vision",
    device_map="auto",
    torch_dtype=torch.float16
)
processor = AutoProcessor.from_pretrained("/models/llama-3.2-vision")
print("Model loaded!")

@app.route('/extract_table', methods=['POST'])
def extract_table():
    data = request.json
    
    # Decode base64 image
    image_data = base64.b64decode(data['image'])
    image = Image.open(io.BytesIO(image_data))
    
    # Prepare prompt
    prompt = """Extract the table from this image and return as JSON.
    
    Format:
    {
      "headers": ["col1", "col2", ...],
      "rows": [
        ["val1", "val2", ...],
        ["val3", "val4", ...]
      ],
      "table_number": "TABLE X.X",
      "confidence": "high/medium/low"
    }
    """
    
    # Run inference
    inputs = processor(images=image, text=prompt, return_tensors="pt").to("cuda")
    
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=1000)
    
    result = processor.decode(output[0], skip_special_tokens=True)
    
    return jsonify({"result": result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
EOF

# Install Flask
pip3 install flask pillow
```

---

### **3.5 Start the server:**

```bash
# Run in background
nohup python3 /root/vision_server.py > /var/log/vision_server.log 2>&1 &

# Check it's running
curl http://localhost:8000/health
```

**Server is now running on port 8000!**

---

## **Phase 4: Connect to Your App** (30 minutes)

### **4.1 Update your backend code:**

```python
# backend/services/self_hosted_ai_service.py

import requests
import base64
from PIL import Image
import io

class SelfHostedAIService:
    def __init__(self, server_url="http://123.45.67.89:8000"):
        self.server_url = server_url
        
    def extract_table(self, image_path_or_pil):
        """Extract table using self-hosted Llama 3.2 Vision"""
        
        # Load image
        if isinstance(image_path_or_pil, str):
            image = Image.open(image_path_or_pil)
        else:
            image = image_path_or_pil
        
        # Convert to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # Send to self-hosted server
        response = requests.post(
            f"{self.server_url}/extract_table",
            json={"image": img_base64},
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"API error: {response.status_code}")
```

---

### **4.2 Update backend/.env:**

```bash
# Switch from OpenAI to self-hosted
USE_SELF_HOSTED_AI=true
SELF_HOSTED_AI_URL=http://123.45.67.89:8000

# Keep OpenAI as backup (fallback if self-hosted fails)
OPENAI_API_KEY=sk-proj-...
```

---

### **4.3 Update ai_table_service.py:**

```python
# backend/services/ai_table_service.py

from config import settings
from .self_hosted_ai_service import SelfHostedAIService

class AITableService:
    def __init__(self):
        if getattr(settings, "use_self_hosted_ai", False):
            self.ai_service = SelfHostedAIService(
                server_url=settings.self_hosted_ai_url
            )
            self.provider = "self-hosted"
        else:
            # Use OpenAI
            self.ai_service = OpenAIService()
            self.provider = "openai"
    
    def extract_table(self, image):
        return self.ai_service.extract_table(image)
```

---

## **Phase 5: Test & Monitor** (15 minutes)

### **5.1 Test extraction:**

```bash
# From your local machine
cd /home/runner/app/backend

python3 << 'EOF'
from services.self_hosted_ai_service import SelfHostedAIService
from PIL import Image

# Test with sample image
ai = SelfHostedAIService(server_url="http://123.45.67.89:8000")

# Extract table from test image
result = ai.extract_table("test_table.png")
print(result)
EOF
```

**Expected output:**
```json
{
  "headers": ["Cable Size", "Current Rating", "Installation Method"],
  "rows": [
    ["1.5mm²", "15A", "Method B"],
    ["2.5mm²", "21A", "Method B"]
  ],
  "confidence": "high"
}
```

---

### **5.2 Monitor costs:**

```bash
# Check GPU usage
nvidia-smi

# Check server uptime
uptime

# View inference logs
tail -f /var/log/vision_server.log
```

---

### **5.3 Benchmark quality:**

Run 10 test extractions, compare with OpenAI:

| Metric | OpenAI gpt-4o-mini | Self-hosted Llama 3.2 |
|--------|-------------------|------------------------|
| Extraction success rate | 95% | 85% |
| Average quality score | 0.65 | 0.55 |
| Cost per document | $9 | $0 (fixed $245/month) |
| Speed | 2-3 sec/page | 1-2 sec/page ✅ |

**Trade-off:** 10-15% lower quality but FREE after fixed cost

---

## 💡 Hybrid Strategy (Best of Both Worlds)

### **Strategy:** Use self-hosted for simple tables, OpenAI for complex

```python
def extract_table_smart(image):
    # Step 1: Quick classification
    complexity = estimate_complexity(image)
    
    if complexity == "simple":
        # 70% of tables: ruled borders, clear structure
        result = self_hosted_ai.extract(image)  # FREE
        
    elif complexity == "complex":
        # 30% of tables: borderless, merged cells
        result = openai_api.extract(image)  # $0.06/page
        
    return result
```

**Cost breakdown (158 pages):**
- 110 simple pages × $0 = $0
- 48 complex pages × $0.06 = $2.88
- GPU server: $245/month (fixed)
- **Total variable cost: ~$3 per document** (vs $9 all-OpenAI)

**Savings at scale:**
- 100 docs/month: $900 (OpenAI) vs $245+$300 = $545 (**-$355 savings**)
- 200 docs/month: $1,800 vs $245+$600 = $845 (**-$955 savings**)

---

## ⚠️ Challenges & Solutions

### **Challenge 1: Model Quality Lower Than GPT-4o**

**Issue:** Self-hosted models are 70-85% as good as GPT-4o

**Solutions:**
1. **Ensemble approach:** Run 2 cheap models, take consensus
2. **Hybrid strategy:** Self-hosted first, OpenAI if low confidence
3. **Fine-tuning:** Train model on your AS3000 data (improves quality 10-20%)
4. **Post-processing:** Use rules to fix common errors

---

### **Challenge 2: Server Management**

**Issue:** Need to monitor uptime, handle crashes

**Solutions:**
1. **Auto-restart:** Use systemd or supervisord
2. **Health checks:** Ping server every 5 minutes
3. **Alerting:** Email/SMS if server down
4. **Fallback:** Auto-switch to OpenAI if self-hosted fails

```python
def extract_with_fallback(image):
    try:
        # Try self-hosted first
        return self_hosted_ai.extract(image)
    except Exception as e:
        logger.warning(f"Self-hosted failed: {e}, falling back to OpenAI")
        return openai_api.extract(image)  # Backup
```

---

### **Challenge 3: Initial Setup Complexity**

**Issue:** 1-2 hours to set up first time

**Solutions:**
1. **Use pre-built Docker images:** RunPod has one-click templates
2. **Hire freelancer:** $50-100 on Upwork for one-time setup
3. **Managed services:** Lambda Labs offers managed inference ($0.50/hour)

---

### **Challenge 4: Model Updates**

**Issue:** Need to download new model versions

**Solutions:**
1. **Automated updates:** Script to check for new versions weekly
2. **Blue-green deployment:** Run old + new model, switch when ready
3. **Stick with stable versions:** Don't always use latest (bleeding edge)

---

## 🔐 Security & Privacy

### **Why Self-Hosting is More Secure:**

**OpenAI API:**
- ❌ Your PDFs go through OpenAI servers
- ❌ Subject to their data retention policies
- ❌ Potential for data leaks
- ❌ Cannot guarantee GDPR/HIPAA compliance

**Self-Hosted:**
- ✅ Data never leaves your server
- ✅ Full control over data retention
- ✅ Can run in private VPC
- ✅ GDPR/HIPAA compliant (you control everything)

**For AS3000 (electrical standards):**
- Not sensitive data, but customers may prefer privacy
- Can be a selling point: "Your PDFs never leave our servers"

---

## 📊 When to Self-Host vs Use API

### **Use OpenAI API when:**
- ✅ Processing < 20 documents/month (not worth fixed cost)
- ✅ Need absolute best quality (GPT-4o > open-source)
- ✅ Don't want to manage infrastructure
- ✅ Variable/unpredictable workload
- ✅ Just testing/prototyping

### **Use Self-Hosted when:**
- ✅ Processing > 30 documents/month (cheaper after fixed cost)
- ✅ Consistent workload (server always utilized)
- ✅ Need data privacy (PDFs don't leave your control)
- ✅ Want 95%+ profit margins
- ✅ Technical expertise to manage servers
- ✅ Long-term business (6+ months)

---

## 🎯 Recommended Timeline

### **Month 1-2: Start with OpenAI API**
- Validate business model
- Get first 10-20 customers
- Optimize extraction pipeline
- **Cost:** $300-600 in API fees

### **Month 3: Test Self-Hosted**
- Rent Vast.ai GPU for 1 month ($245)
- Run side-by-side with OpenAI
- Compare quality & costs
- **Investment:** $245 (one month trial)

### **Month 4: Hybrid Approach**
- Self-hosted for simple tables (70%)
- OpenAI for complex tables (30%)
- **Cost:** $245 (fixed) + $300 (variable) = $545
- **vs full OpenAI:** $1,800
- **Savings:** $1,255/month (70% reduction)

### **Month 6+: Full Self-Hosted**
- Once quality acceptable, switch fully
- Keep OpenAI as emergency fallback only
- **Cost:** $245/month (vs $4,500 with OpenAI)
- **Savings:** $4,255/month (95% reduction)

---

## 💼 Real-World Case Study

### **SaaS Company: DocuExtract (fictional but realistic)**

**Business:** PDF table extraction service

**Timeline:**

**Months 1-3 (OpenAI only):**
- Customers: 50 → 100 → 200
- API costs: $450 → $900 → $1,800
- Revenue: $1,000 → $2,000 → $4,000
- Profit: $550 → $1,100 → $2,200 (50% margin)

**Month 4 (Added self-hosted):**
- Customers: 300
- GPU cost: $245 (fixed)
- OpenAI cost: $540 (30% of requests)
- Revenue: $6,000
- Profit: $5,215 (87% margin) ✅

**Month 12 (Fully self-hosted):**
- Customers: 1,000
- GPU cost: $245 (fixed)
- OpenAI cost: $0 (fallback only, unused)
- Revenue: $20,000
- Profit: $19,255 (96% margin) ✅✅

**Cumulative savings:** $100,000+ in first year

---

## 🛠️ Simplified Setup (Alternative)

### **Use Pre-Built Services (Easier but More Expensive):**

**1. Modal.com** - Serverless GPU functions
- Pay per second of GPU use
- No server management
- $0.30-0.50 per document (cheaper than OpenAI)
- https://modal.com

**2. Replicate** - Hosted open-source models
- Pre-deployed Llama, LLaVA, etc.
- Simple API like OpenAI
- $0.10-0.20 per document
- https://replicate.com

**3. Together.ai** - Open-source model API
- Llama 3.2 Vision available
- $0.08 per document (80% cheaper than OpenAI)
- https://together.ai

**Recommendation:** Start with Together.ai (easiest, no setup, 80% cheaper than OpenAI)

---

## ✅ Action Plan for You

### **Option A: Quick Win (Use Together.ai)** ⭐ **RECOMMENDED FOR NOW**

**Setup time:** 10 minutes

```bash
# 1. Sign up: https://together.ai
# 2. Get API key
# 3. Update backend/.env:

TOGETHER_AI_API_KEY=your_key_here
TOGETHER_MODEL=meta-llama/Llama-3.2-11B-Vision-Instruct
```

```python
# 4. Update ai_table_service.py:
import together

def extract_table(image):
    response = together.Image.create(
        model="meta-llama/Llama-3.2-11B-Vision-Instruct",
        prompt="Extract table as JSON...",
        image=image
    )
    return response
```

**Cost:** $0.08 per document (90% cheaper than gpt-4o-mini at $0.90)

**For 158-page PDF:**
- Together.ai: 158 × $0.01 = **$1.58**
- OpenAI: 158 × $0.06 = **$9.48**
- **Savings: $7.90 (83%)** ✅

---

### **Option B: Full Self-Host (Month 3+)** 

**When:** After you have 30+ customers (break-even point)

**Steps:**
1. Rent Vast.ai RTX 4090 ($245/month)
2. Follow setup guide above (1-2 hours)
3. Test quality on 10 documents
4. Switch 70% of traffic to self-hosted
5. Keep OpenAI for complex tables

**Expected savings:** $1,000-4,000/month depending on volume

---

## 📚 Resources

### **Learning:**
- Hugging Face Model Hub: https://huggingface.co/models
- Llama 3.2 Vision: https://huggingface.co/meta-llama/Llama-3.2-11B-Vision-Instruct
- LLaVA: https://llava-vl.github.io/

### **GPU Providers:**
- Vast.ai: https://vast.ai (cheapest)
- RunPod: https://runpod.io (easiest)
- Lambda Labs: https://lambdalabs.com (premium)
- Modal: https://modal.com (serverless)

### **Alternative APIs (Pre-hosted open-source):**
- Together.ai: https://together.ai (recommended)
- Replicate: https://replicate.com
- Fireworks.ai: https://fireworks.ai

### **Communities:**
- r/LocalLLaMA (Reddit)
- Hugging Face Discord
- Together.ai Discord

---

## 🎯 Summary

### **Self-Hosted AI is:**

✅ **Much cheaper** at scale ($245/month fixed vs $9/doc variable)  
✅ **More private** (data never leaves your server)  
✅ **Faster** (no API latency)  
✅ **Higher margins** (95%+ profit after break-even)  
✅ **Scalable** (unlimited docs for fixed cost)  

❌ **Requires setup** (1-2 hours initial)  
❌ **Slightly lower quality** (70-85% of GPT-4o)  
❌ **Needs monitoring** (server management)  
❌ **Higher fixed cost** (not worth it for <20 docs/month)  

---

### **Best Path for You:**

**Now (Month 1-2):**
- Use **Together.ai** API ($0.08/doc vs OpenAI $0.90/doc)
- 90% cost savings with zero setup
- Test quality with your AS3000 PDFs

**Month 3+ (After 30+ customers):**
- Rent GPU server on **Vast.ai** ($245/month)
- Deploy **Llama 3.2 Vision** (follow guide above)
- Keep Together.ai as fallback
- 95%+ profit margin on AI costs

**Month 6+ (After 100+ customers):**
- Consider buying own GPU ($1,600 one-time)
- Monthly cost drops to $50 (electricity only)
- 99% profit margin on AI costs

---

**Want me to help you set up Together.ai (10-minute quick win)?** Or would you rather wait until Month 3+ and go straight to full self-hosting?
