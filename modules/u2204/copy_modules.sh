#!/bin/bash

# Variables
IMAGE_NAME=ms-u2204-kernel-modules-source-image
CONTAINER_NAME=ms-u2204-kernel-modules-source-container

# Check if the image exists
if ! docker image inspect "$IMAGE_NAME" > /dev/null 2>&1; then
    echo "Docker image $IMAGE_NAME not found. Building the image..."

    # Replace with the actual Docker build command
    docker build -t $IMAGE_NAME .

    if [ $? -ne 0 ]; then
        echo "Failed to build the Docker image."
        exit 1
    fi
else
    echo "Docker image $IMAGE_NAME exists."
fi

# Check if the container already exists and stop/remove it if necessary
if docker ps -a --format '{{.Names}}' | grep -q "^$CONTAINER_NAME\$"; then
    echo "Container $CONTAINER_NAME already exists. Removing it..."
    docker rm -f $CONTAINER_NAME
fi


# Create and start the container
echo "Creating and starting container $CONTAINER_NAME..."
docker create --name $CONTAINER_NAME $IMAGE_NAME
docker start -a $CONTAINER_NAME

# Ensure the target directory exists
mkdir -p files

# Copy files from the container to the host
docker cp $CONTAINER_NAME:/workspace/linux-5.15.0/vmlinux files/
docker cp $CONTAINER_NAME:/workspace/output/lib/modules/5.15.167 files/

# Stop and remove the container after the copy operation
echo "Stopping and removing the container..."
docker stop "$CONTAINER_NAME"
docker rm "$CONTAINER_NAME"
