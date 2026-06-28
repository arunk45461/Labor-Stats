# Labor-Stats 📊

> **Labor Analytics Solution** — A full AWS data pipeline that ingests BLS labor statistics and US population data, performs analytics, and automates everything with AWS CDK.

---

## Architecture Diagram

```
For detailed architecture diagram, refer "architecture-diagram-labor-stats.jpg" file

┌─────────────────────────────────────────────────────────────────────────────┐
│                        Labor-Stats AWS Data Pipeline                         │
└─────────────────────────────────────────────────────────────────────────────┘

  SOURCES                      INGEST LAMBDA (daily)           S3 BUCKET
  ───────                      ─────────────────────           ─────────
                               ┌─────────────────────┐
  https://download.bls.gov ──► │ Part 1: BLS Sync     │──────► bls/pr/*
  pub/time.series/pr/          │  • Scrape directory  │        (all files)
                               │  • MD5 dedup check   │
  [User-Agent header fix]      │  • Upload new/changed│
                               │  • Delete removed    │
  https://honolulu-api ──────► │ Part 2: Population   │──────► population/
  .datausa.io/tesseract/       │  • Fetch JSON API    │        us_population.json
  data.jsonrecords             │  • Save to S3        │
                               └─────────────────────┘
                                         ▲
                                         │ triggers daily (06:00 UTC)
                               ┌─────────────────────┐
                               │  Amazon EventBridge  │
                               │  (Scheduled Rule)    │
                               └─────────────────────┘

  S3 BUCKET                    SQS QUEUE               ANALYTICS LAMBDA
  ─────────                    ─────────               ────────────────
  population/             S3 Event           SQS
  us_population.json ──► Notification ────► Queue ──► Part 3: Analytics
  (ObjectCreated)                                       │
                                                        │  Report 1: Population mean + stddev (2013-2018)
                                                        │  Report 2: Best year per BLS series_id
                                                        │  Report 3: PRS30006032 Q01 + Population join
                                                        │
                                                        └──► CloudWatch Logs
                                                             (results logged here)

  ┌──────────────────────────────────────────────────────────────────────────┐
  │  AWS Services Used                                                        │
  │  • Amazon S3            — Data lake storage                               │
  │  • AWS Lambda (×2)      — Serverless compute (Python 3.12)               │
  │  • Amazon SQS           — Decoupled trigger queue                         │
  │  • Amazon EventBridge   — Daily cron schedule                             │
  │  • AWS CDK (Python)     — Infrastructure as Code                          │
  │  • Amazon CloudWatch    — Logs & monitoring                               │
  └──────────────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
Labor-Stats/
├── src/
│   ├── part1/
│   │   └── bls_sync.py          # BLS S3 sync (403 fix included)
│   ├── part2/
│   │   └── population_api.py    # DataUSA population API → S3
│   ├── part3/
│   │   └── analytics.py         # Pandas analytics reports
│   └── part4/
│       └── pipeline_lambda.py   # Combined Lambda handler (Part 1 + 2)
├── notebooks/
│   └── analytics.ipynb          # Interactive analytics (Part 3 submission)
├── infrastructure/
│   └── app.py                   # AWS CDK stack definition
├── build_layer.sh               # Script to build Lambda dependency layer
├── cdk.json                     # CDK configuration
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
└── README.md                    # This file
```

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.12 | [python.org](https://python.org) |
| Node.js | ≥ 18 | [nodejs.org](https://nodejs.org) (required for CDK CLI) |
| AWS CLI | ≥ 2.x | [AWS docs](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| AWS CDK CLI | ≥ 2.x | `npm install -g aws-cdk` |
| Git | any | [git-scm.com](https://git-scm.com) |

---

## Quick Start — Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/Labor-Stats.git
cd Labor-Stats
```

### 2. Open in VS Code

```bash
code .
```

Install the recommended VS Code extensions when prompted (Python, Jupyter).

### 3. Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure AWS credentials

```bash
aws configure
# Enter your AWS Access Key ID, Secret Key, default region (e.g. us-east-1)
```

Or copy `.env.example` → `.env` and fill in your values:

```bash
cp .env.example .env
# Edit .env with your AWS account ID and region
```

### 6. Run Part 1 locally (BLS data sync)

```bash
export S3_BUCKET_NAME=labor-stats-data-<your-account-id>
python src/part1/bls_sync.py
```

> **Note:** An S3 bucket with that name must already exist, or deploy the CDK stack first (Step 12 below).

### 7. Run Part 2 locally (Population API)

```bash
python src/part2/population_api.py
```

### 8. Run Part 3 locally (Analytics)

```bash
python src/part3/analytics.py
```

### 9. Run the Jupyter notebook (Part 3 submission)

```bash
pip install jupyter
jupyter notebook notebooks/analytics.ipynb
```

---

## Deploying to AWS with CDK

### 10. Bootstrap CDK (one-time per account/region)

```bash
cdk bootstrap aws://<your-account-id>/us-east-1
```

### 11. Build the Lambda dependency layer

CDK needs the Python packages pre-packaged in a `lambda_layer/` directory:

```bash
chmod +x build_layer.sh
./build_layer.sh
```

This downloads `requests`, `beautifulsoup4`, and `pandas` compiled for Amazon Linux (Python 3.12) into `lambda_layer/python/`.

### 12. Deploy the full stack

```bash
cdk deploy
```

CDK will show you the planned changes. Type `y` to confirm. After a few minutes you will see outputs like:

```
Outputs:
LaborStatsPipelineStack.BucketName    = labor-stats-data-123456789012
LaborStatsPipelineStack.QueueUrl      = https://sqs.us-east-1.amazonaws.com/...
LaborStatsPipelineStack.IngestLambdaArn    = arn:aws:lambda:...
LaborStatsPipelineStack.AnalyticsLambdaArn = arn:aws:lambda:...
```
For detailed understanding of the "cdk deploy" command, kindly refer "detailed-steps-cdk-deploy.docx"

### 13. Verify the deployment

```bash
# List files in S3 after manual Lambda invocation
aws s3 ls s3://labor-stats-data-<account-id>/bls/pr/ --recursive

# Manually invoke the ingest Lambda
aws lambda invoke \
    --function-name LaborStatsPipelineStack-IngestLambda \
    --payload '{}' \
    response.json
cat response.json

# Check CloudWatch logs for analytics output
aws logs tail /aws/lambda/LaborStatsPipelineStack-AnalyticsLambda --follow
```

### 14. Tear down (when done)

```bash
cdk destroy
```

> The S3 bucket is set to `RemovalPolicy.RETAIN` — it will not be deleted automatically to protect your data. Delete it manually if needed: `aws s3 rb s3://labor-stats-data-<account-id> --force`

---

## Known Issues & Fixes

### 🔴 BLS 403 Forbidden Error

**Problem:** `requests.get("https://download.bls.gov/pub/time.series/pr/")` returns HTTP 403.

**Cause:** The Bureau of Labor Statistics blocks automated requests that don't identify themselves. Per [BLS data access policy](https://www.bls.gov/bls/pss.htm):

> *"BLS also reserves the right to block robots that do not contain information that can be used to contact the owner."*

**Fix (already applied in `src/part1/bls_sync.py`):** Add a `User-Agent` header with your contact information:

```python
HEADERS = {
    "User-Agent": "YourProjectName/1.0 (your@email.com)"
}
response = requests.get(BLS_BASE_URL, headers=HEADERS)
```

Update the contact email in `bls_sync.py` to your own before deploying.

---

### 🔴 BLS Data Whitespace / Join Mismatch

**Problem:** Filters and joins on `series_id` or `period` return empty results even when the data looks correct.

**Cause:** BLS tab-separated files contain trailing whitespace in column values. For example, `series_id` may be stored as `"PRS30006032 "` (with a trailing space).

**Fix (already applied in `src/part1/bls_sync.py` and `src/part3/analytics.py`):**

```python
# Strip whitespace from all string columns after loading
for col in df.columns:
    df[col] = df[col].str.strip()
```

---

### 🔴 Lambda Timeout on Large BLS Sync

**Problem:** The BLS directory contains many files; the ingest Lambda may time out with the default 3-second limit.

**Fix (already applied in `infrastructure/app.py`):** Lambda timeout is set to 10 minutes:

```python
timeout=Duration.minutes(10),
memory_size=512,
```

---

### 🔴 SQS Visibility Timeout Must Match Lambda Timeout

**Problem:** SQS may re-deliver messages if the Lambda takes longer than the queue's visibility timeout.

**Fix (already applied):** SQS `visibility_timeout` is set to match the Lambda timeout (300 seconds).

---

## What Was Built (Submission Checklist)

| Part | Deliverable | Location |
|------|-------------|----------|
| **Part 1** | BLS data republished to S3 | `s3://labor-stats-data-<account>/bls/pr/` |
| **Part 1** | Sync script (no hardcoded names, MD5 dedup) | `src/part1/bls_sync.py` |
| **Part 2** | Population API fetch + S3 JSON | `src/part2/population_api.py` |
| **Part 3** | Analytics notebook (.ipynb) | `notebooks/analytics.ipynb` |
| **Part 4** | CDK Infrastructure as Code | `infrastructure/app.py` |
| **Part 4** | Ingest Lambda (daily schedule) | `src/part4/pipeline_lambda.py` |
| **Part 4** | SQS queue (S3 → SQS notification) | `infrastructure/app.py` |
| **Part 4** | Analytics Lambda (SQS trigger) | `src/part3/analytics.py` |

---

## AI Usage Disclosure

This project used AI for generating this repo. Prompts included requests to:
- Generate the full project structure and CDK stack based on the quest README
- Scaffold the BLS scraping logic with the 403 User-Agent fix
- Write the Pandas analytics queries for the three reports
- Create this README with architecture diagram

All code was reviewed and validated for correctness. The BLS whitespace trimming fix, MD5 deduplication logic, and SQS/Lambda wiring are correct solutions to the problems described in the quest hints.

---

## License

MIT
