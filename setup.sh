#!/bin/bash
# ============================================================================
# Setup Script for Knowledge Base Search API
# ============================================================================
# Initializes environment and starts the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

echo -e "${GREEN}Knowledge Base Search API - Setup${NC}"
echo "=================================="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found. Please install Docker.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker found${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ Docker Compose not found. Please install Docker Compose.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose found${NC}"

# Check .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}→ Creating .env from template...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}⚠ Edit .env with your actual credentials${NC}"
fi

# Create init-scripts directory if not exists
mkdir -p init-scripts

# Build images
echo -e "${GREEN}Building Docker images...${NC}"
docker-compose build

# Start services
echo -e "${GREEN}Starting services...${NC}"
docker-compose up -d

# Wait for services
echo -e "${GREEN}Waiting for services to be healthy...${NC}"
max_attempts=30
attempt=1

until curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; do
    if [ $attempt -ge $max_attempts ]; then
        echo -e "${RED}✗ Services failed to start${NC}"
        docker-compose logs search-api | tail -20
        exit 1
    fi
    echo "  Attempt $attempt/$max_attempts..."
    sleep 2
    ((attempt++))
done

echo -e "${GREEN}✓ All services are healthy${NC}"

# Display endpoints
echo ""
echo -e "${GREEN}Setup Complete!${NC}"
echo "=================================="
echo ""
echo "API Endpoints:"
echo "  - API:        http://localhost:8000"
echo "  - Swagger:    http://localhost:8000/docs"
echo "  - ReDoc:      http://localhost:8000/redoc"
echo "  - Health:     http://localhost:8000/api/v1/health"
echo ""
echo "Services:"
echo "  - PostgreSQL: localhost:5432"
echo "  - Meilisearch: http://localhost:7700"
echo "  - Qdrant:     http://localhost:6333"
echo "  - Redis:      localhost:6379"
echo ""
echo "Useful Commands:"
echo "  - View logs:     docker-compose logs -f search-api"
echo "  - Stop services: docker-compose down"
echo "  - Run tests:     pytest test_api.py -v"
echo ""
