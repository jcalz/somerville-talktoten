```
Amazon EC2 lightsail
amazon linux micro thingy

sudo yum update
# get emacs
sudo yum install -y emacs

# get x11
sudo yum install -y xterm
sudo yum install -y xorg-x11-xauth.x86_64 xorg-x11-server-utils.x86_64 dbus-x11.x86_64
emacs ~/.bashrc
# add these lines:
# sudo xauth add $(xauth -f ~ec2-user/.Xauthority list|tail -1)
# export EDITOR=emacs

sudo emacs /etc/sysconfig/clock
>> ZONE="America/New_York"
sudo ln -sf /usr/share/zoneinfo/America/New_York /etc/localtime
sudo reboot

# get python 3
sudo yum install -y python35
sudo yum install -y python35-virtualenv
sudo alternatives --set python /usr/bin/python3.5

# get apache
sudo yum install -y httpd24
sudo yum install -y mod24_ssl
sudo yum install -y mod24_wsgi-python35.x86_64

sudo service httpd start
sudo chkconfig httpd on

# get ssl cert
wget https://dl.eff.org/certbot-auto
chmod a+x certbot-auto
sudo mv certbot-auto /usr/local/bin/certbot-auto
sudo /usr/local/bin/certbot-auto --debug #ugh
# ui (talktoten.stephanieforsomerville.com, jcalz@mit.edu, ssl.conf, Secure)

sudo su
export EDITOR=emacs
crontab -e
>> 20 1,13 * * * /usr/local/bin/certbot-auto renew --quiet --no-self-upgrade

# also do this for some reason since httpd won't restart properly
sudo chmod 0755 /etc/letsencrypt/live
sudo chmod 0755 /etc/letsencrypt/archive

# get git
sudo yum -y install git

# put files here
# get ssh key and upload to bitbucket TODO
git clone git@bitbucket.org:jcalz/campaign.git ~/Campaign

chmod a+x manage.py

#get libjpeg
sudo yum -y install libjpeg-devel

# user is ec2-user
cd ~/Campaign
virtualenv Campaignenv
source Campaignenv/bin/activate
# pip install --upgrade pip <-- don't do this!  I think it messes stuff up
pip install django
pip install django-extensions
pip install django-import-export
pip install python-dateutil
pip install six
pip install wheel
pip install reportlab



---

# I tried and failed to use mod_wsgi.  It kept saying it couldn't find
# the encodings module, indicating something about the python config was
# messed up.  After a few hours, I gave up.  I will just use the django test
# server for now, and use apache to proxy to that server.  Here it is:

emacs /home/ec2-user/start-campaign-django.sh
#the following lines are the file contents

#!/bin/bash
cd /home/ec2-user/Campaign/Campaignenv
. bin/activate
cd /home/ec2-user/Campaign
nohup sh -c "echo \"starting server\"; while true; do python manage.py runserver 0.0.0.0:8000 ; sleep 1; echo \"server unexpectedly stopped, restarting\"; done" >> /home/ec2-user/django.log 2>&1 &

# add this script to crontab for reboots
export EDITOR=emacs
crontab -e
#add this line
@reboot /home/ec2-user/start-campaign-django.sh

sudo emacs /etc/httpd/conf.d/ssl.conf
# ProxyPass /error-docs/ !
# ProxyPass / http://127.0.0.1:8000
# ProxyPass / "http://127.0.0.1:8000/" retry=0 
# ErrorDocument 503 /error-docs/503.html

---
# add suitable 503.html document under /var/www/html/error-docs/503.html
(https://gist.github.com/jcalz/2c0a01c04ff2403d536510daf50eb8bd)


General update procedure

# kill django
# make backup copy of db
# git pull
# manage.py migrate
# restart django
# load_data.py (if there's data to load)

```