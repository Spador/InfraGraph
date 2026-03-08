# sample.tf — InfraGraph test fixture
# Designed to exercise both explicit (depends_on) and implicit (interpolation)
# dependency inference in the Terraform parser.
#
# Expected resources (11):
#   data.aws_ami.ubuntu
#   aws_vpc.main
#   aws_subnet.private
#   aws_security_group.app
#   aws_instance.app
#   aws_s3_bucket.uploads
#   aws_iam_role.app_role
#   aws_iam_policy.s3_access
#   variable.region
#   variable.instance_type
#   output.instance_ip
#   output.bucket_name
#
# Expected edges (minimum 7):
#   aws_subnet.private        → aws_vpc.main              (implicit: vpc_id ref)
#   aws_security_group.app    → aws_vpc.main              (implicit: vpc_id ref)
#   aws_instance.app          → data.aws_ami.ubuntu       (implicit: ami ref)
#   aws_instance.app          → aws_subnet.private        (implicit: subnet_id ref)
#   aws_instance.app          → aws_security_group.app    (implicit: sg ref)
#   aws_iam_role.app_role     → aws_s3_bucket.uploads     (explicit: depends_on)
#   aws_iam_policy.s3_access  → aws_s3_bucket.uploads     (implicit: arn ref)
#   output.instance_ip        → aws_instance.app          (implicit: value ref)
#   output.bucket_name        → aws_s3_bucket.uploads     (implicit: value ref)

# ── Data Sources ────────────────────────────────────────────────────────────

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-*-22.04-amd64-server-*"]
  }
}

# ── Core Network ────────────────────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "infragraph-vpc"
  }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "infragraph-private"
  }
}

resource "aws_security_group" "app" {
  name        = "infragraph-app-sg"
  description = "Security group for the application server"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── Compute ─────────────────────────────────────────────────────────────────

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.private.id
  vpc_security_group_ids = [aws_security_group.app.id]

  tags = {
    Name = "infragraph-app"
  }
}

# ── Storage ─────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "uploads" {
  bucket = "infragraph-uploads"

  tags = {
    Name = "infragraph-uploads"
  }
}

# ── IAM ─────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "app_role" {
  name = "infragraph-app-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  depends_on = [aws_s3_bucket.uploads]
}

resource "aws_iam_policy" "s3_access" {
  name        = "infragraph-s3-access"
  description = "Allow access to uploads bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject"]
      Resource = "${aws_s3_bucket.uploads.arn}/*"
    }]
  })
}

# ── Variables ────────────────────────────────────────────────────────────────

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "instance_ip" {
  description = "Public IP of the application instance"
  value       = aws_instance.app.public_ip
}

output "bucket_name" {
  description = "Name of the uploads S3 bucket"
  value       = aws_s3_bucket.uploads.bucket
}
