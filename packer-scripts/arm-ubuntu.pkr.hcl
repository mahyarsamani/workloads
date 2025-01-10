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
  default = "arm-ubuntu"
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
      iso_url       = "https://old-releases.ubuntu.com/releases/jammy/ubuntu-22.04-live-server-arm64.iso"
      iso_checksum  = "sha256:c209ab013280d3cd26a344def60b7b19fbb427de904ea285057d94ca6ac82dd5"
      output_dir    = "arm-disk-image-2204"
      http_directory = "http/arm-2204"
    }
    "24.04" = {
      iso_url       = "https://cdimage.ubuntu.com/releases/24.04/release/ubuntu-24.04.1-live-server-arm64.iso"
      iso_checksum  = "sha256:5ceecb7ef5f976e8ab3fffee7871518c8e9927ec221a3bb548ee1193989e1773"
      output_dir    = "arm-disk-image-2404"
      http_directory = "http/arm-2404"
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
  boot_command     = [
                      "c<wait>",
                      "linux /casper/vmlinuz autoinstall ds=nocloud-net\\;s=http://{{.HTTPIP}}:{{.HTTPPort}}/ --- ",
                      "<enter><wait>",
                      "initrd /casper/initrd",
                      "<enter><wait>",
                      "boot",
                      "<enter>",
                      "<wait>"
                      ]
  cpus             = "32"
  disk_size        = "21600"
  format           = "raw"
  headless         = "true"
  http_directory   = local.iso_data[var.ubuntu_version].http_directory
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
  vm_name          = "${var.image_name}"
  ssh_handshake_attempts = "1000"
}

build {
  sources = ["source.qemu.initialize"]

  provisioner "file" {
    destination = "/home/gem5/"
    source      = "files/exit.sh"
  }

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
    source      = "files/serial-getty@.service"
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
    source      = "annotate/lib"
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
    destination = "/home/gem5/workloads/annotate/"
    source      = "annotate/gem5"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "branson"
  }

  provisioner "file" {
    destination = "/home/gem5/workloads/"
    source      = "cache_ubench"
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
    scripts         = ["scripts/post-installation.sh"]
    environment_vars = ["ISA=arm64"]
    expect_disconnect = true
  }

}
