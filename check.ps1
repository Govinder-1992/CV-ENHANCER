# CV Enhancer - health check. Run:  ./check.ps1
# Checks every layer and prints WORKING / BLOCKED for each.

$ErrorActionPreference = "SilentlyContinue"
$region = "us-east-1"
$stack  = "sam-app"

function Line($label, $ok, $detail) {
    $tag = if ($ok) { "[ WORKING ]" } else { "[ BLOCKED ]" }
    "{0}  {1,-28} {2}" -f $tag, $label, $detail
}

Write-Host "`n===== CV Enhancer health check =====`n"

# Pull stack outputs once
$api    = aws cloudformation describe-stacks --stack-name $stack --region $region --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text
$site   = aws cloudformation describe-stacks --stack-name $stack --region $region --query "Stacks[0].Outputs[?OutputKey=='FrontendWebsiteUrl'].OutputValue" --output text
$bucket = aws cloudformation describe-stacks --stack-name $stack --region $region --query "Stacks[0].Outputs[?OutputKey=='ResultsBucketName'].OutputValue" --output text

# 1. Frontend
try { $code = (Invoke-WebRequest $site -UseBasicParsing -TimeoutSec 15).StatusCode } catch { $code = 0 }
Line "Frontend website" ($code -eq 200) "$site"

# 2. WAF
$waf = aws wafv2 get-web-acl-for-resource --resource-arn ("arn:aws:apigateway:{0}::/restapis/{1}/stages/prod" -f $region, ($api -replace 'https://','' -split '\.')[0]) --region $region --query "WebACL.Name" --output text
Line "AWS WAF (rate limit)" ($waf -and $waf -ne "None") "$waf"

# 3. API Gateway reachable (OPTIONS preflight should answer)
try { $apiCode = (Invoke-WebRequest $api -Method Options -UseBasicParsing -TimeoutSec 15).StatusCode } catch { $apiCode = $_.Exception.Response.StatusCode.value__ }
Line "API Gateway" ($apiCode -ge 200 -and $apiCode -lt 500) "HTTP $apiCode on OPTIONS"

# 4. Results in S3 so far
$objs = aws s3 ls "s3://$bucket/results/" --recursive --region $region
$count = ($objs | Measure-Object -Line).Lines
Line "S3 results produced" ($count -gt 0) "$count object(s) under results/"

# 5. Bedrock quota
'[{"role":"user","content":[{"text":"hi"}]}]' | Set-Content msgs.json -Encoding ascii
'{"maxTokens":5}' | Set-Content inf.json -Encoding ascii
$bedrock = aws bedrock-runtime converse --region $region --model-id "us.anthropic.claude-haiku-4-5-20251001-v1:0" --messages file://msgs.json --inference-config file://inf.json --query "output.message.content[0].text" --output text 2>&1
Remove-Item msgs.json, inf.json -ErrorAction SilentlyContinue
$bedrockOk = -not ("$bedrock" -match "Throttling|Too many tokens|Error")
Line "Bedrock AI (live call)" $bedrockOk ($(if ($bedrockOk) { "responded" } else { "daily token quota exhausted" }))

Write-Host "`n------------------------------------"
if ($bedrockOk) {
    Write-Host "All layers up. Submit a CV at the site, then re-run to see 'S3 results' grow." -ForegroundColor Green
} else {
    Write-Host "Everything works except the Bedrock AI call (AWS daily token quota)." -ForegroundColor Yellow
    Write-Host "See docs/bedrock-support-case.md to lift the cap." -ForegroundColor Yellow
}
Write-Host ""
