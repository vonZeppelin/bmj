Vagrant.configure("2") do |config|
  config.vm.box = "debian/stretch64"
  config.vm.box_check_update = false
  config.vm.network "public_network", bridge: "en0: Wi-Fi (AirPort)"

  config.vm.provider "virtualbox" do |vb|
    vb.name = "mopidy-debug"
    vb.memory = "1024"

    vb.customize ["modifyvm", :id, '--audio', "coreaudio", "--audiocontroller", "ac97"]
    vb.customize ["modifyvm", :id, "--usb", "on"]
    vb.customize ["modifyvm", :id, "--usbehci", "on"]
    vb.customize [
      "usbfilter", "add", "0",
      "--target", :id,
      "--name", "External DVD/RW",
      "--vendorid", "0x152d",
      "--productid", "0x2339"
    ]
  end

  config.vm.provision "shell", inline: <<-SHELL
      apt-get update
      apt-get install -y git libdiscid0 mopidy python-pip
      pip install git+https://github.com/vonZeppelin/bmj#egg=mopidy-cd&subdirectory=mopidy-cd
  SHELL

end
