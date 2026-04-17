#!/bin/bash
set -e

# === CONFIG ===
SERVER="${SERVER:-100.119.201.30}"
USER="${USER:-clement}"
PROJECT_DIR="yt-transcript-app"
BACKEND_IMAGE="yt-transcript-backend:latest"
FRONTEND_IMAGE="yt-transcript-frontend:latest"
BACKEND_CONTAINER="yt-transcript-backend"
FRONTEND_CONTAINER="yt-transcript-frontend"
BACKEND_PORT="8001"
FRONTEND_PORT="3001"
REMOTE_DIR="/home/clement/yt-transcript-app"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKEND_TAR="yt-transcript-backend_${TIMESTAMP}.tar"
FRONTEND_TAR="yt-transcript-frontend_${TIMESTAMP}.tar"

echo "==> Deploying yt-transcript-app to ${USER}@${SERVER}"

# === PRE-CHECKS ===
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo "ERROR: Run this script from the yt-transcript-app project root."
    exit 1
fi

# === 1. Build Docker images locally ===
echo "🔧 Building backend Docker image..."
docker build -t "${BACKEND_IMAGE}" ./backend

echo "🔧 Building frontend Docker image..."
docker build -t "${FRONTEND_IMAGE}" ./frontend

# === 2. Save images as tar files ===
echo "📦 Saving backend image to ${BACKEND_TAR}..."
docker save -o "${BACKEND_TAR}" "${BACKEND_IMAGE}"

echo "📦 Saving frontend image to ${FRONTEND_TAR}..."
docker save -o "${FRONTEND_TAR}" "${FRONTEND_IMAGE}"

# Cleanup local tars on exit
_cleanup_local() {
    rm -f "${BACKEND_TAR}" "${FRONTEND_TAR}" || true
}
trap _cleanup_local EXIT

# === 3. Copy images to remote server ===
echo "📤 Copying backend image to ${USER}@${SERVER}..."
scp "${BACKEND_TAR}" "${USER}@${SERVER}:~/"

echo "📤 Copying frontend image to ${USER}@${SERVER}..."
scp "${FRONTEND_TAR}" "${USER}@${SERVER}:~/"

# === 4. Deploy on remote server ===
echo "🚀 Deploying containers on remote server..."
ssh "${USER}@${SERVER}" bash -e <<EOF
set -euo pipefail

BACKEND_IMAGE="${BACKEND_IMAGE}"
FRONTEND_IMAGE="${FRONTEND_IMAGE}"
BACKEND_CONTAINER="${BACKEND_CONTAINER}"
FRONTEND_CONTAINER="${FRONTEND_CONTAINER}"
BACKEND_PORT="${BACKEND_PORT}"
FRONTEND_PORT="${FRONTEND_PORT}"
REMOTE_DIR="${REMOTE_DIR}"
BACKEND_TAR="${BACKEND_TAR}"
FRONTEND_TAR="${FRONTEND_TAR}"

# Create remote project directory
mkdir -p "\${REMOTE_DIR}/backend_cache"

echo "-> Loading backend image..."
docker load -i "\${BACKEND_TAR}"

echo "-> Loading frontend image..."
docker load -i "\${FRONTEND_TAR}"

echo "-> Stopping existing containers..."
docker stop "\${BACKEND_CONTAINER}" >/dev/null 2>&1 || true
docker stop "\${FRONTEND_CONTAINER}" >/dev/null 2>&1 || true

echo "-> Removing existing containers..."
docker rm "\${BACKEND_CONTAINER}" >/dev/null 2>&1 || true
docker rm "\${FRONTEND_CONTAINER}" >/dev/null 2>&1 || true

echo "-> Running backend container..."
docker run -d \
    --name "\${BACKEND_CONTAINER}" \
    -p \${BACKEND_PORT}:8000 \
    -v "\${REMOTE_DIR}/backend_cache:/tmp/video_cache" \
    --restart unless-stopped \
    "\${BACKEND_IMAGE}"

echo "-> Running frontend container..."
docker run -d \
    --name "\${FRONTEND_CONTAINER}" \
    -p \${FRONTEND_PORT}:3000 \
    --restart unless-stopped \
    "\${FRONTEND_IMAGE}"

echo "-> Cleaning up remote tar files..."
rm -f "\${BACKEND_TAR}" "\${FRONTEND_TAR}" || true

echo "✅ Backend deployed: http://${SERVER}:\${BACKEND_PORT}"
echo "✅ Frontend deployed: http://${SERVER}:\${FRONTEND_PORT}"
EOF

echo ""
echo "✅ Deployment complete!"
echo "   Frontend: http://${SERVER}:${FRONTEND_PORT}"
echo "   Backend API: http://${SERVER}:${BACKEND_PORT}"
echo ""
echo "   View backend logs: ssh ${USER}@${SERVER} 'docker logs -f ${BACKEND_CONTAINER}'"
echo "   View frontend logs: ssh ${USER}@${SERVER} 'docker logs -f ${FRONTEND_CONTAINER}'"
