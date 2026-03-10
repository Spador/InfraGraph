# seed/main.tf — InfraGraph demo infrastructure
#
# A realistic AWS environment that demonstrates the dependency graph.
# Resources are connected via both explicit depends_on and implicit
# interpolation references — showing what InfraGraph can visualise.
#
# Expected dependency edges (implicit unless noted):
#   aws_subnet.private        → aws_vpc.main              (vpc_id ref)
#   aws_subnet.public         → aws_vpc.main              (vpc_id ref)
#   aws_security_group.alb    → aws_vpc.main              (vpc_id ref)
#   aws_security_group.app    → aws_vpc.main              (vpc_id ref)
#   aws_lb.main               → aws_security_group.alb    (sg ref)
#   aws_lb.main               → aws_subnet.public         (subnet ref)
#   aws_instance.app          → data.aws_ami.ubuntu       (ami ref)
#   aws_instance.app          → aws_subnet.private        (subnet_id ref)
#   aws_instance.app          → aws_security_group.app    (sg ref)
#   aws_iam_role.app_role     → aws_s3_bucket.assets      (explicit depends_on)
#   aws_iam_policy.s3_read    → aws_s3_bucket.assets      (arn ref)
#   output.instance_ip        → aws_instance.app
#   output.bucket_name        → aws_s3_bucket.assets

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-*-22.04-amd64-server-*"]
  }
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name    = "infragraph-vpc"
    Project = "infragraph"
  }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${var.region}a"

  tags = {
    Name = "infragraph-private"
    Tier = "private"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.10.0/24"
  availability_zone       = "${var.region}b"
  map_public_ip_on_launch = true

  tags = {
    Name = "infragraph-public"
    Tier = "public"
  }
}

resource "aws_security_group" "alb" {
  name        = "infragraph-alb-sg"
  description = "Security group for the Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS from internet"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "infragraph-alb-sg" }
}

resource "aws_security_group" "app" {
  name        = "infragraph-app-sg"
  description = "Security group for application instances"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "Traffic from ALB"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "infragraph-app-sg" }
}

resource "aws_lb" "main" {
  name               = "infragraph-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public.id]

  tags = { Name = "infragraph-alb" }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.private.id
  vpc_security_group_ids = [aws_security_group.app.id]

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = {
    Name    = "infragraph-app"
    Project = "infragraph"
  }
}

resource "aws_s3_bucket" "assets" {
  bucket = "infragraph-assets"

  tags = {
    Name    = "infragraph-assets"
    Project = "infragraph"
  }
}

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

  depends_on = [aws_s3_bucket.assets]

  tags = { Name = "infragraph-app-role" }
}

resource "aws_iam_policy" "s3_read" {
  name        = "infragraph-s3-read"
  description = "Read access to the assets bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:ListBucket"]
      Resource = [
        "${aws_s3_bucket.assets.arn}",
        "${aws_s3_bucket.assets.arn}/*"
      ]
    }]
  })
}

output "instance_ip" {
  description = "Public IP of the application instance"
  value       = aws_instance.app.public_ip
}

output "bucket_name" {
  description = "Name of the assets S3 bucket"
  value       = aws_s3_bucket.assets.bucket
}

output "alb_dns" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}
