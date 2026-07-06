locals {
  tags = { Service = "commerce" }
}

module "storefront" {
  source = "../../modules/static_site"
  name   = "${var.project_name}-storefront"
  tags   = local.tags
}

module "budget" {
  source            = "../../modules/budget"
  name              = "${var.project_name}-monthly"
  monthly_limit_usd = var.monthly_budget_usd
  alert_email       = var.alert_email
}

resource "aws_s3_bucket" "media" {
  bucket = "${var.project_name}-media"
  tags   = local.tags
}

resource "aws_ecr_repository" "api" {
  name                 = "${var.project_name}-api"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project_name}-api"
  retention_in_days = 14
}

data "aws_vpc" "default" { default = true }
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "alb" {
  name   = "${var.project_name}-alb"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port   = 80
    to_port     = 80
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

resource "aws_security_group" "api" {
  name   = "${var.project_name}-api"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port       = 8001
    to_port         = 8001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "database" {
  name   = "${var.project_name}-database"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.project_name}-postgres"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "postgres" {
  identifier                 = "${var.project_name}-postgres"
  engine                     = "postgres"
  engine_version             = "16"
  instance_class             = "db.t4g.micro"
  allocated_storage          = 20
  max_allocated_storage      = 30
  db_name                    = "matcha"
  username                   = "matcha"
  password                   = var.database_password
  multi_az                   = false
  publicly_accessible        = false
  backup_retention_period    = 7
  deletion_protection        = false
  skip_final_snapshot        = true
  auto_minor_version_upgrade = true
  storage_encrypted          = true
  db_subnet_group_name       = aws_db_subnet_group.postgres.name
  vpc_security_group_ids     = [aws_security_group.database.id]
  tags                       = local.tags
}

resource "aws_secretsmanager_secret" "api" {
  name = "${var.project_name}/api"
}

resource "aws_secretsmanager_secret_version" "api" {
  secret_id = aws_secretsmanager_secret.api.id
  secret_string = jsonencode({
    APP_SECRET   = "replace-after-provisioning-with-32-random-characters"
    DATABASE_URL = "postgresql+psycopg://matcha:${var.database_password}@${aws_db_instance.postgres.address}:5432/matcha"
  })
}

resource "aws_iam_role" "ecs_execution" {
  name = "${var.project_name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "secrets" {
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.api.arn
    }]
  })
}

resource "aws_ecs_cluster" "api" { name = var.project_name }

resource "aws_lb" "api" {
  name               = "${var.project_name}-api"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-api"
  port        = 8001
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_vpc.default.id
  health_check { path = "/healthz" }
}

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  container_definitions = jsonencode([{
    name      = "api"
    image     = "${aws_ecr_repository.api.repository_url}:latest"
    essential = true
    portMappings = [{ containerPort = 8001, protocol = "tcp" }]
    environment = [
      { name = "ENVIRONMENT", value = "demo" },
      { name = "COOKIE_SECURE", value = "true" },
      { name = "MEDIA_BUCKET", value = aws_s3_bucket.media.id }
    ]
    secrets = [
      { name = "APP_SECRET", valueFrom = "${aws_secretsmanager_secret.api.arn}:APP_SECRET::" },
      { name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.api.arn}:DATABASE_URL::" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.api.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8001
  }
  depends_on = [aws_lb_listener.api]
}

resource "aws_sesv2_email_identity" "sender" {
  email_identity = var.ses_sender
}
