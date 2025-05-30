# Start from Ubuntu 24.04 base image
FROM ubuntu:24.04

# Install necessary packages for kernel and module build
RUN apt update && apt install -y \
    build-essential \
    libncurses-dev \
    bison \
    flex \
    libssl-dev \
    libelf-dev \
    bc \
    wget \
    git \
    kmod


RUN sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources
RUN apt update
RUN mkdir /workspace
RUN cd /workspace && apt source linux-image-unsigned-6.8.0-47-generic

RUN cd /workspace/linux-6.8.0 && \
    make defconfig && \
    make -j 32 && \
    make INSTALL_MOD_PATH=/workspace/output modules_install

RUN git clone https://github.com/nkrim/gem5.git --depth=1 --filter=blob:none --no-checkout --sparse --single-branch --branch=gem5-bridge && \
    cd gem5 && \
    git sparse-checkout add util/m5 && \
    git sparse-checkout add util/gem5_bridge && \
    git sparse-checkout add include && \
    git checkout

RUN cd gem5/util/gem5_bridge && \
    make KMAKEDIR=/workspace/linux-6.8.0 INSTALL_MOD_PATH=/workspace/output build install

RUN cd /workspace/output/lib/modules/6.8.12 && \
    rm -rf build

# Use bash as the default shell
CMD ["/bin/bash"]
