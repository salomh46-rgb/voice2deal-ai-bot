#!/bin/bash
set -e

echo "============================================="
echo "🚀 Voice2Deal AI - VPS O'rnatish & Ishga Tushirish"
echo "============================================="

# 1. Update system & install dependencies
echo "📦 Tizim paketlari yangilanmoqda..."
sudo apt-get update && sudo apt-get install -y git python3 python3-pip curl

# 2. Check for Docker
if ! command -v docker &> /dev/null; then
    echo "🐳 Docker o'rnatilmoqda..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
fi

# 3. Check for Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "🐳 Docker Compose o'rnatilmoqda..."
    sudo apt-get install -y docker-compose-plugin || sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose
fi

# 4. Prepare data folders
mkdir -p data reports

# 5. Build and run container
echo "🚀 Docker konteyner ishga tushirilmoqda..."
docker compose down || true
docker compose up -d --build

echo "============================================="
echo "✅ Voice2Deal AI Bot VPS da muvaffaqiyatli ishga tushdi!"
echo "📋 Loglarni ko'rish uchun: docker compose logs -f"
echo "============================================="
