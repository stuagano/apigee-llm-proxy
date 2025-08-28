#!/bin/bash

# Enterprise AI Gateway - Git Repository Setup Script

echo "Setting up Git repository for Enterprise AI Gateway..."

# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Enterprise AI Gateway

- FastAPI application with Cloud Run deployment
- Multi-provider LLM proxy architecture  
- Enterprise authentication framework
- Production-ready Docker container
- Comprehensive documentation and examples

Features:
- Async FastAPI application with structured logging
- Cloud Run deployment with auto-scaling
- Health checks and monitoring endpoints
- Placeholder LLM provider integrations
- Development tooling (Makefile, Docker)

Ready for:
- Authentication implementation (SSO, service accounts)
- LLM provider integrations (Azure, AWS, Google)
- Infrastructure as Code (Terraform)
- Monitoring and observability setup"

# Instructions for GitHub
echo ""
echo "Repository initialized locally!"
echo ""
echo "Next steps to push to GitHub:"
echo "1. Create a new repository on GitHub named 'enterprise-ai-gateway'"
echo "2. Run these commands:"
echo ""
echo "   git remote add origin https://github.com/YOUR_USERNAME/enterprise-ai-gateway.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "Repository is ready to push!"