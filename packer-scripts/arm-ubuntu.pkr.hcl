packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "~> 1"
    }
  }
}

variable "image_name" {
  type    = string
}

variable "ssh_password" {
  type    = string
  default = "12345"
}

variable "ssh_username" {
  type    = string
  default = "gem5"
}

variable "ubuntu_version" {
  type    = string
  default = "24.04"
  validation {
    condition     = contains(["22.04", "24.04"], var.ubuntu_version)
    error_message = "Ubuntu version must be either 22.04 or 24.04."
  }
}

locals {
  iso_data = {
    "22.04" = {
      iso_url       = "https://cloud-images.ubuntu.com/releases/jammy/release-20260515/ubuntu-22.04-server-cloudimg-arm64.img"
      iso_checksum  = "file:https://cloud-images.ubuntu.com/releases/jammy/release-20260515/SHA256SUMS"
      output_dir    = "${var.image_name}-2204"
    }
    "24.04" = {
      iso_url       = "https://cloud-images.ubuntu.com/releases/noble/release-20260518/ubuntu-24.04-server-cloudimg-arm64.img"
      iso_checksum  = "file:https://cloud-images.ubuntu.com/releases/noble/release-20260518/SHA256SUMS"
      output_dir    = "${var.image_name}-2404"
    }
  }
}

variable "use_kvm" {
  type    = string
  default = "true"
  validation {
    condition     = contains(["true", "false"], var.use_kvm)
    error_message = "KVM option must be either 'true' or 'false'."
  }
}

locals {
  qemuargs_base = [
    ["-boot", "order=dc"],
    ["-bios", "./files/flash0.img"],
    ["-machine", "virt"],
    ["-machine", "gic-version=3"],
    ["-device", "virtio-gpu-pci"],
    ["-device", "qemu-xhci"],
    ["-device", "usb-kbd"],
  ]

  qemuargs_kvm = concat(local.qemuargs_base,[
    ["-cpu", "host"],
    ["-enable-kvm"]
  ])

  qemuargs_no_kvm = concat(local.qemuargs_base,[
    ["-cpu", "cortex-a57"]
  ])

  qemuargs = var.use_kvm == "true" ? local.qemuargs_kvm : local.qemuargs_no_kvm
}

source "qemu" "initialize" {
  disk_image       = true
  cd_files         = ["packer-scripts/cloud-init/user-data", "packer-scripts/cloud-init/meta-data"]
  cd_label         = "cidata"
  cpus             = "32"
  disk_size        = "64000"
  format           = "raw"
  headless         = "true"
  iso_checksum     = local.iso_data[var.ubuntu_version].iso_checksum
  iso_urls         = [local.iso_data[var.ubuntu_version].iso_url]
  memory           = "65536"
  output_directory = local.iso_data[var.ubuntu_version].output_dir
  qemu_binary      = "/usr/bin/qemu-system-aarch64"
  qemuargs         = local.qemuargs
  shutdown_command = "echo '${var.ssh_password}'|sudo -S shutdown -P now"
  ssh_password     = "${var.ssh_password}"
  ssh_username     = "${var.ssh_username}"
  ssh_wait_timeout = "60m"
  vm_name          = "disk-image"
  ssh_handshake_attempts = "1000"
}

build {
  sources = ["source.qemu.initialize"]

  provisioner "file" {
    destination = "/home/gem5/"
    source      = "files/arm/gem5_init.sh"
  }

  provisioner "file" {
    destination = "/home/gem5/"
    source      = "files/arm/after_boot.sh"
  }

  provisioner "file" {
    destination = "/home/gem5/"
    source      = "files/serial-getty@.service-override.conf"
  }

  provisioner "file" {
    destination = "/home/gem5/"
    source      = "files/00-default.preset"
  }

  provisioner "file" {
    destination = "/home/gem5/"
    source      = "files/10-enable-essential.preset"
  }

  provisioner "file" {
    destination = "/home/gem5"
    source      = "modules/u2204/files/5.15.167"
  }

  provisioner "file" {
    destination = "/home/gem5"
    source      = "modules/u2404/files/6.8.12"
  }

  provisioner "shell" {
    inline = [
      "mkdir -p /home/gem5/workloads",
      "mkdir -p /home/gem5/workloads/annotate",
    ]
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/annotate/"
    source      = "annotate/include"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/annotate/"
    source      = "annotate/annotate.c"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/annotate/"
    source      = "annotate/Makefile"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "hov"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "branson"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "hpcg"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "NPB3.4-OMP"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "NPB3.4-MPI"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "simple-vector-bench"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "spatter-traces"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "UME"
  }

  provisioner "shell" {
    execute_command = "echo '${var.ssh_password}' | {{ .Vars }} sudo -E -S bash '{{ .Path }}'"
    scripts         = ["scripts/install-driver.sh", "scripts/install-packages.sh"]
    environment_vars = ["ISA=arm64", "DISTRO_VERSION=${var.ubuntu_version}", "DEBIAN_FRONTEND=noninteractive"]
    expect_disconnect = true
  }

  provisioner "shell" {
    scripts = ["scripts/install-benchmarks.sh"]
  }

  provisioner "shell" {
    execute_command = "echo '${var.ssh_password}' | {{ .Vars }} sudo -E -S bash '{{ .Path }}'"
    scripts         = ["scripts/install-gem5-init.sh", "scripts/disable-services.sh"]
    expect_disconnect = true
  }
}
