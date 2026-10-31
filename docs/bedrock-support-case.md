# AWS Support case — lift Bedrock daily token limit

Use this to open a **free** AWS Support case and get the account-level Bedrock
"too many tokens per day" cap removed.

## Root cause (confirmed via Service Quotas)

The per-day token quotas for Bedrock are set to **0** and marked
**non-adjustable** for this account. For example:

| Quota | Code | Value | Adjustable |
| ----- | ---- | ----- | ---------- |
| Model invocation max tokens per day for Amazon Nova 2 Lite | `L-210172B5` | `0` | **No** |
| Model invocation max tokens per day for Amazon Nova Micro  | `L-D2912E70` | `0` | **No** |
| Global cross-region inference tokens per day – Nova 2 Lite | `L-AD940EDE` | `0` | **No** |

Because the value is `0` and the quota is **non-adjustable**, it **cannot** be
raised through Service Quotas or `aws service-quotas
request-service-quota-increase`. Only AWS can lift it, via account verification
or a support case. A `0` cap almost always means the account is still in a
new / unverified / free-trial state.

## Billing is already verified — go straight to the support case

This account **already has a valid, verified payment method** (Visa on file,
with a backup payment method enabled) and is a standard paid account — it is
NOT a free-trial or unverified account. Despite that, the Bedrock per-day token
quota is still `0` and non-adjustable.

That means the usual "add a payment method" step does not apply here. The cap is
most likely a **new-account Bedrock ramp** (a time-based limit AWS applies to
recently created accounts, independent of billing). The reliable way to clear it
is the Account & Billing support case below — **do not wait**, and make sure the
case states that billing is already verified so support does not deflect to
"add a payment method."

## How to open the support case

1. Sign in as the account owner.
2. **Support** → **Support Center** → **Create case**
   (https://support.console.aws.amazon.com/support/home#/case/create).
3. Choose **Account and billing** (free on the Basic support plan).
4. Fill in the fields below.

### Case fields

**Service:** Amazon Bedrock

**Subject:**

```
Bedrock daily token quota is 0 and non-adjustable (us-east-1) - please enable on-demand usage
```

**Description:**

```
Account ID: 870755687933
Region: us-east-1

Account status: This is a standard paid account with a VERIFIED payment method
(Visa on file, plus a backup payment method enabled). It is NOT a free-trial or
unverified account, so "add a payment method" does not apply.

Problem: All Amazon Bedrock Converse API calls fail with:
  ThrottlingException: "Too many tokens per day, please wait before trying again."

Evidence from Service Quotas (us-east-1):
- "Model invocation max tokens per day for Amazon Nova 2 Lite" (L-210172B5)
  shows Value = 0 and Adjustable = false.
- The same is true for every other per-day token quota (Nova Micro L-D2912E70,
  Nova 2 Lite global L-AD940EDE, etc.) - all 0 and non-adjustable.

Details:
- Fails even at maxTokens = 1 (a trivial request).
- Affects every model (Amazon Nova 2 Lite, Nova Micro, Anthropic Claude) so it
  is account-wide, not model-specific.
- Persists across multiple days; it does not reset.
- Because the quota is non-adjustable, I cannot raise it via Service Quotas or
  request-service-quota-increase.

Request:
Billing is already verified, so please remove or raise the account-level Bedrock
daily token limit (currently 0, non-adjustable) so I can use Amazon Bedrock
on-demand inference. If this is a new-account ramp, please lift it or tell me
the exact timeline/condition to clear it.

Use case:
A personal "CV Enhancer" project that calls Bedrock to analyze and improve a CV
against a job description. Low volume (a few requests at a time).
```

**Severity:** General guidance (or lowest available).

## After the cap is lifted — verify and test

Re-run the quota check (the stack currently uses Nova 2 Lite):

```powershell
cd "C:\Users\govin\OneDrive\Desktop\CV ENHANCER"
Set-Content msgs.json '[{"role":"user","content":[{"text":"hi"}]}]' -Encoding ascii
Set-Content inf.json '{"maxTokens":5}' -Encoding ascii
aws bedrock-runtime converse --region us-east-1 `
  --model-id "us.amazon.nova-2-lite-v1:0" `
  --messages file://msgs.json --inference-config file://inf.json `
  --query "output.message.content[0].text" --output text
Remove-Item msgs.json,inf.json
```

When that prints a reply (instead of ThrottlingException):

1. Start the frontend locally and submit a CV:
   ```powershell
   python -m http.server 8080   # open http://localhost:8080
   ```
2. Watch the worker:
   ```powershell
   sam logs --stack-name sam-app --name WorkerFunction --region us-east-1 --tail
   ```
3. Confirm the output in S3 (bucket name from stack outputs):
   ```powershell
   aws cloudformation describe-stacks --stack-name sam-app --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='ResultsBucketName'].OutputValue" --output text
   aws s3 ls s3://<ResultsBucketName>/results/ --recursive --region us-east-1
   ```

Seeing `enhanced-cv.txt` + `analysis.json` means the full pipeline works end to end.

## Meanwhile: demonstrate the pipeline without tokens (mock mode)

```powershell
cd "C:\Users\govin\OneDrive\Desktop\CV ENHANCER"
sam deploy --config-file samconfig.toml --parameter-overrides "MockBedrock=true" --no-confirm-changeset
# submit a CV, confirm files in S3, then turn it back off:
sam deploy --config-file samconfig.toml --parameter-overrides "MockBedrock=false" --no-confirm-changeset
```
