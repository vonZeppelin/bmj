Vagrant.configure("2") do |config|
  config.vm.box = "debian/stretch64"
  config.vm.box_check_update = false
  config.vm.network "forwarded_port", guest: 6680, host: 6680
  config.vm.network "forwarded_port", guest: 6600, host: 6600

  config.vm.provider "virtualbox" do |vb|
    vb.name = "mopidy-debug"
    vb.memory = "1024"

    # vb.customize ["modifyvm", :id, '--audio', "coreaudio", "--audiocontroller", "ac97"]
    # vb.customize ["modifyvm", :id, "--usb", "on"]
    # vb.customize ["modifyvm", :id, "--usbehci", "on"]
    # vb.customize [
    #   "usbfilter", "add", "0",
    #   "--target", :id,
    #   "--name", "External DVD/RW",
    #   "--vendorid", "0x152d",
    #   "--productid", "0x2339"
    # ]
    # vb.customize [
    #   "storageattach", :id,
    #   "--storagectl", "SATA Controller",
    #   "--port", "5",
    #   "--type", "dvddrive",
    #   "--medium", "disk.cue"
    # ]
  end

  config.vm.provision "shell", inline: <<-SHELL
      apt update
      apt install -y git libdiscid0 mopidy python-pip
      pip install mopidy-cd
  SHELL

end
