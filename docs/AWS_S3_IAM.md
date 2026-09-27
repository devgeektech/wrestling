# AWS S3 + IAM role setup (Wrestling Guide / Vision Quest)

## Your environment

| Item | Value |
|------|--------|
| Bucket | `vision-quest-ai-videos` |
| Region | `eu-north-1` (Europe Stockholm) |
| IAM role | `VisionQuestEC2S3Role` |

Uploads (videos, profile images, analysis frames) go to S3 when `USE_S3=True`.
On EC2, attach **VisionQuestEC2S3Role** as the instance profile — do **not** put access keys in `.env`.

## Checklist on AWS

### 1. S3 bucket `vision-quest-ai-videos`
- Region: `eu-north-1`
- **Block Public Access**: ON (recommended)
- Object Ownership: Bucket owner enforced

### 2. Bucket CORS (for Flutter / browser video players)

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["Accept-Ranges", "Content-Range", "Content-Length", "Content-Type", "ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

### 3. IAM role `VisionQuestEC2S3Role`

Trust: `ec2.amazonaws.com`. Policy should allow at least:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MediaBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::vision-quest-ai-videos"
    },
    {
      "Sid": "MediaObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::vision-quest-ai-videos/*"
    }
  ]
}
```

Attach this role to the EC2 instance as an **instance profile**.

### 4. App `.env` on the EC2 server

```env
USE_S3=True
AWS_STORAGE_BUCKET_NAME=vision-quest-ai-videos
AWS_S3_REGION_NAME=eu-north-1
AWS_QUERYSTRING_AUTH=True
```

Do **not** set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on EC2.

Locally keep `USE_S3=False` unless you intentionally use temporary keys for testing.

## How the app uses S3

| Item | Behavior |
|------|----------|
| Upload | Django writes to S3 via `django-storages` |
| `file_url` in API | S3 URL (signed if `AWS_QUERYSTRING_AUTH=True`) |
| Gemini / ffmpeg | Downloads object to a temp file, then analyzes |
| Local `/media/` | Used only when `USE_S3=False` (dev) |
