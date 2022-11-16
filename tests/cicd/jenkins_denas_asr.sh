#!/bin/bash

# init conda env
eval "$('/opt/intel/oneapi/intelpython/latest/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
conda activate pytorch-1.10.0

# launch denas for transformer-based asr
cd /home/vmagent/app/e2eaiok/DeNas
sed -i '/max_epochs:/ s/:.*/: 1/' ../conf/denas/asr/e2eaiok_denas_asr.conf
python -u search.py --domain asr --conf ../conf/denas/asr/e2eaiok_denas_asr.conf
cd /home/vmagent/app/e2eaiok

# test
LANG=C tests/cicd/bats/bin/bats tests/cicd/test_denas.bats