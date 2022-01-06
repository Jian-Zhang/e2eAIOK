import subprocess
import yaml
import logging
import time
import sys
from common.utils import *

from SDA.modeladvisor.BaseModelAdvisor import BaseModelAdvisor


class RNNTAdvisor(BaseModelAdvisor):
    def __init__(self, dataset_meta_path, train_path, eval_path, settings):
        super().__init__(dataset_meta_path, train_path, eval_path, settings)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger('sigopt')

        # set default required arguments
        self.init_default_params()
        
        # check distributed configuration
        missing_params = []
        if self.params["ppn"] > 1:
            missing_params = missing_params + \
                ['hosts'] if 'hosts' not in self.params else missing_params
            missing_params = missing_params + \
                ['iface'] if 'iface' not in self.params else missing_params
        if len(missing_params) > 0:
            raise ValueError(
                f"[CONFIG ERROR] Missing parameters {missing_params} in \
                hydroai_defaults.conf when ppn is set above 1.")

        self.train_path = train_path
        self.test_path = eval_path
        self.dataset_meta_path = dataset_meta_path
        self.parse_meta_file(self.dataset_meta_path)
        self.saved_path = self.params['save_path']
        self.train_python = "/opt/intel/oneapi/intelpython/latest/envs/pytorch_1.10/bin/python"
        self.train_script = "/home/vmagent/app/hydro.ai/modelzoo/rnnt/pytorch/train.py"

    def init_default_params(self):
        self.params[
            'ppn'] = 1 if 'ppn' not in self.params else self.params['ppn']
        self.params[
            'num_instances'] = 1 if 'num_instances' not in self.params else self.params[
                'num_instances']
        self.params[
            'num_cores'] = 1 if 'num_cores' not in self.params else self.params[
                'num_cores']
        self.params['metric'] = {
            'name': 'WER',
            'threshold': 0.058
        } if 'metric' not in self.params else self.params['metric']

        self.params['beta1'] = 0.9 if 'beta1' not in self.params else self.params['beta1']
        self.params['beta2'] = 0.999 if 'beta2' not in self.params else self.params['beta2']
        self.params['max_duration'] = 16.7 if 'max_duration' not in self.params else self.params['max_duration']
        self.params['min_lr'] = 1e-5 if 'min_lr' not in self.params else self.params['min_lr']
        self.params['lr_exp_gamma'] = 0.939 if 'lr_exp_gamma' not in self.params else self.params['lr_exp_gamma']
        self.params['epochs'] = 80 if 'epochs' not in self.params else self.params['epochs']
        self.params['epochs_this_job'] = 0 if 'epochs_this_job' not in self.params else self.params['epochs_this_job']
        self.params['ema'] = 0.995 if 'ema' not in self.params else self.params['ema']
        self.params['model_config'] = 'modelzoo/rnnt/pytorch/configs/baseline_v3-1023sp.yaml' if 'model_config' not in self.params else self.params['model_config']
        self.params['dali_device'] = 'cpu' if 'dali_device' not in self.params else self.params['dali_device']
        self.params['weight_decay'] = 1e-3 if 'weight_decay' not in self.params else self.params['weight_decay']
        self.params['grad_accumulation_steps'] = 1 if 'grad_accumulation_steps' not in self.params else self.params['grad_accumulation_steps']
        self.params['weights_init_scale'] = 0.5 if 'weights_init_scale' not in self.params else self.params['weights_init_scale']
        self.params['seed'] = 30677 if 'seed' not in self.params else self.params['seed']
        self.params['max_symbol_per_sample'] = 300 if 'max_symbol_per_sample' not in self.params else self.params['max_symbol_per_sample']
        self.params['data_cpu_threads'] = 16 if 'data_cpu_threads' not in self.params else self.params['data_cpu_threads']
        self.params['min_seq_split_len'] = 20 if 'min_seq_split_len' not in self.params else self.params['min_seq_split_len']
        self.params['log_frequency'] = 1 if 'log_frequency' not in self.params else self.params['log_frequency']
        self.params['val_frequency'] = 1 if 'val_frequency' not in self.params else self.params['val_frequency']
        self.params['prediction_frequency'] = 1000000 if 'prediction_frequency' not in self.params else self.params['prediction_frequency']

    def parse_meta_file(self, meta_file):
        with open(meta_file) as f:
            meta = yaml.load(f, Loader=yaml.FullLoader)
        print(meta)
        self.train_manifests = meta['train_manifests']
        self.val_manifests = meta['val_manifests']
    
    def update_metrics(self):
        result_metrics_file = os.path.join(self.saved_path, "metric.txt")
        if not os.path.exists(result_metrics_file):
            raise FileNotFoundError(
                f"{self.train_script} completed, while we can't find \
                    result {result_metrics_file} file.")
        with open(result_metrics_file) as f:
            metric = f.readlines()
        metrics = []
        metrics.append({
            'name': self.params['metric']['name'],
            'value': float(metric[-1])
        })
        metrics.append({'name': 'training_time', 'value': self.training_time})
        self.params['model_parameter']['metrics'] = metrics
        return self.params['model_parameter']['metrics']

    def initialize_model_parameter(self, assignments=None):
        config = {}
        tuned_parameters = {}
        if assignments:
            tuned_parameters['enc_n_hid'] = assignments[
                'enc_n_hid']
            tuned_parameters['enc_rnn_layers'] = assignments[
                'enc_rnn_layers']
            tuned_parameters['enc_stack_time_factor'] = assignments[
                'enc_stack_time_factor']
            tuned_parameters['pred_n_hid'] = assignments[
                'pred_n_hid']
            tuned_parameters['pred_rnn_layers'] = assignments[
                'pred_rnn_layers']
            tuned_parameters['joint_n_hid'] = assignments[
                'joint_n_hid']
            tuned_parameters['learning_rate'] = assignments['learning_rate']
            tuned_parameters['warmup_epochs'] = assignments['warmup_epochs']
            tuned_parameters['hold_epochs'] = assignments['hold_epochs']
        else:
            tuned_parameters['enc_n_hid'] = 1024
            tuned_parameters['enc_rnn_layers'] = 2
            tuned_parameters['enc_stack_time_factor'] = 2
            tuned_parameters['pred_n_hid'] = 512
            tuned_parameters['pred_rnn_layers'] = 2
            tuned_parameters['joint_n_hid'] = 512
            tuned_parameters['learning_rate'] = float(0.007)
            tuned_parameters['warmup_epochs'] = 6
            tuned_parameters['hold_epochs'] = 33
        config['tuned_parameters'] = tuned_parameters
        self.params['model_parameter'] = config
        self.params['model_saved_path'] = os.path.join(
            self.params['save_path'], get_hash_string(str(tuned_parameters)))
        return config

    def generate_sigopt_yaml(self, file='test_sigopt.yaml'):
        config = {}
        config['project'] = self.params['model_parameter']['project']
        config['experiment'] = self.params['model_parameter']['experiment']
        parameters = [{
            'name': 'enc_n_hid',
            'grid': [64, 128, 256, 512],
            'type': 'int'
        }, {
            'name': 'enc_rnn_layers',
            'bounds':{
                'min': 1,
                'max': 3
            },
            'type': 'int'
        }, {
            'name': 'enc_stack_time_factor',
            'bounds': {
                'min': 1,
                'max': 4
            },
            'type': 'int'
        }, {
            'name': 'pred_n_hid',
            'grid': [64, 128, 256, 512],
            'type': 'int'
        }, {
            'name': 'pred_rnn_layers',
            'bounds': {
                'min': 1,
                'max': 3
            },
            'type': 'int'
        }, {
            'name': 'joint_n_hid',
            'grid': [64, 128, 256, 512],
            'type': 'int'
        }, {
            'name': 'learning_rate',
            'bounds': {
                'min': 1.0e-4,
                'max': 1.0e-1
            },
            'type': 'double',
            'transformation': 'log'
        }, {
            'name': 'warmup_epochs',
            'bounds': {
                'min': 1,
                'max': 8
            },
            'type': 'int'
        }, {
            'name': 'hold_epochs',
            'bounds': {
                'min': 10,
                'max': 60
            },
            'type': 'int'
        }]
        user_defined_parameter = self.params['model_parameter'][
            'parameters'] if ('model_parameter' in self.params) and (
                'parameters' in self.params['model_parameter']) else None
        config['parameters'] = parameters
        if user_defined_parameter:
            self.logger.info(
                f"Update with user defined parameters {user_defined_parameter}"
            )
            update_list(config['parameters'], user_defined_parameter)
        config['metrics'] = [{
            'name': 'WER',
            'strategy': 'optimize',
            'objective': 'maximize',
            'threshold': 0.058
        }, {
            'name': 'training_time',
            'objective': 'minimize',
            'threshold': 18000
        }]
        user_defined_metrics = self.params['model_parameter']['metrics'] if (
            'model_parameter' in self.params) and (
                'metrics' in self.params['model_parameter']) else None
        if user_defined_metrics:
            self.logger.info(
                f"Update with user defined parameters {user_defined_metrics}")
            update_list(config['metrics'], user_defined_metrics)
        config['observation_budget'] = self.params['observation_budget']

        saved_path = os.path.join(self.params['save_path'], file)
        with open(saved_path, 'w') as f:
            yaml.dump(config, f)
        return config

    def train_model(self, args):
        start_time = time.time()
        self.apply_model_params()
        if args['ppn'] > 1:
            self.dist_launch(args)
        else:
            self.launch(args)
        self.training_time = time.time() - start_time
        metrics = self.update_metrics()
        model_path = args['model_saved_path']
        return self.training_time, model_path, metrics

    def dist_launch(self, args):
        ppn = args['ppn']
        hosts = args['hosts']

        # construct rnnt launch command
        cmd = f"{self.train_python} -m intel_extension_for_pytorch.cpu.launch --distributed --nproc_per_node={ppn} --nnodes={len(hosts)} --hostfile {','.join(hosts)} "
        cmd += f"{self.train_script} "
        cmd += f"--output_dir {self.saved_path} "
        cmd += f"--use_ipex --dist --dist_backend ccl "
        cmd += f"--batch_size {args['train_batch_size']} "
        cmd += f"--val_batch_size {args['eval_batch_size']} "
        cmd += f"--lr {args['model_parameter']['tuned_parameters']['learning_rate']} "
        cmd += f"--warmup_epochs {args['model_parameter']['tuned_parameters']['warmup_epochs']} "
        cmd += f"--hold_epochs {args['model_parameter']['tuned_parameters']['hold_epochs']} "
        cmd += f"--beta1 {args['beta1']} "
        cmd += f"--beta2 {args['beta2']} "
        cmd += f"--max_duration {args['max_duration']} "
        cmd += f"--target {args['metric']['threshold']} "
        cmd += f"--min_lr {args['min_lr']} "
        cmd += f"--lr_exp_gamma {args['lr_exp_gamma']} "
        cmd += f"--epochs {args['epochs']} "
        cmd += f"--epochs_this_job {args['epochs_this_job']} "
        cmd += f"--ema {args['ema']} "
        cmd += f"--model_config {args['model_config']} "
        cmd += f"--train_dataset_dir {self.train_path} "
        cmd += f"--valid_dataset_dir {self.test_path} "
        cmd += f"--dali_device {args['dali_device']} "
        cmd += f"--weight_decay {args['weight_decay']} "
        cmd += f"--grad_accumulation_steps {args['grad_accumulation_steps']} "
        cmd += f"--weights_init_scale {args['weights_init_scale']} "
        cmd += f"--seed {args['seed']} "
        cmd += f"--train_manifests {' '.join(self.train_manifests)} "
        cmd += f"--val_manifests {' '.join(self.val_manifests)} "
        cmd += f"--vectorized_sa --vectorized_sampler --multilayer_lstm --enable_prefetch --tokenized_transcript --dist_sampler --pre_sort_for_seq_split --jit_tensor_formation "
        cmd += f"--max_symbol_per_sample {args['max_symbol_per_sample']} "
        cmd += f"--data_cpu_threads {args['data_cpu_threads']} "
        cmd += f"--min_seq_split_len {args['min_seq_split_len']} "
        cmd += f"--log_frequency {args['log_frequency']} "
        cmd += f"--val_frequency {args['val_frequency']} "
        cmd += f"--prediction_frequency {args['prediction_frequency']} "
        self.logger.info(f'training launch command: {cmd}')

        process = subprocess.Popen(cmd, shell=True)
        process.wait()

    def launch(self, args):
        # construct rnnt launch command
        cmd = f"{self.train_python} -m intel_extension_for_pytorch.cpu.launch --throughput_mode "
        cmd += f"{self.train_script} "
        cmd += f"--output_dir {self.saved_path} "
        cmd += f"--use_ipex "
        cmd += f"--batch_size {args['train_batch_size']} "
        cmd += f"--val_batch_size {args['eval_batch_size']} "
        cmd += f"--lr {args['model_parameter']['tuned_parameters']['learning_rate']} "
        cmd += f"--warmup_epochs {args['model_parameter']['tuned_parameters']['warmup_epochs']} "
        cmd += f"--hold_epochs {args['model_parameter']['tuned_parameters']['hold_epochs']} "
        cmd += f"--beta1 {args['beta1']} "
        cmd += f"--beta2 {args['beta2']} "
        cmd += f"--max_duration {args['max_duration']} "
        cmd += f"--target {args['metric']['threshold']} "
        cmd += f"--min_lr {args['min_lr']} "
        cmd += f"--lr_exp_gamma {args['lr_exp_gamma']} "
        cmd += f"--epochs {args['epochs']} "
        cmd += f"--epochs_this_job {args['epochs_this_job']} "
        cmd += f"--ema {args['ema']} "
        cmd += f"--model_config {args['model_config']} "
        cmd += f"--train_dataset_dir {self.train_path} "
        cmd += f"--valid_dataset_dir {self.test_path} "
        cmd += f"--dali_device {args['dali_device']} "
        cmd += f"--weight_decay {args['weight_decay']} "
        cmd += f"--grad_accumulation_steps {args['grad_accumulation_steps']} "
        cmd += f"--weights_init_scale {args['weights_init_scale']} "
        cmd += f"--seed {args['seed']} "
        cmd += f"--train_manifests {' '.join(self.train_manifests)} "
        cmd += f"--val_manifests {' '.join(self.val_manifests)} "
        cmd += f"--vectorized_sa --vectorized_sampler --multilayer_lstm --enable_prefetch --tokenized_transcript --dist_sampler --pre_sort_for_seq_split --jit_tensor_formation "
        cmd += f"--max_symbol_per_sample {args['max_symbol_per_sample']} "
        cmd += f"--data_cpu_threads {args['data_cpu_threads']} "
        cmd += f"--min_seq_split_len {args['min_seq_split_len']} "
        cmd += f"--log_frequency {args['log_frequency']} "
        cmd += f"--val_frequency {args['val_frequency']} "
        cmd += f"--prediction_frequency {args['prediction_frequency']} "
        self.logger.info(f'training launch command: {cmd}')

        process = subprocess.Popen(cmd, shell=True)
        process.wait()

    def apply_model_params(self):
        config_file = self.params['model_config']
        with open(config_file, 'r') as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
            config['rnnt']['enc_n_hid'] = self.params['model_parameter']['tuned_parameters']['enc_n_hid']
            config['rnnt']['enc_pre_rnn_layers'] = self.params['model_parameter']['tuned_parameters']['enc_rnn_layers']
            config['rnnt']['enc_post_rnn_layers'] = self.params['model_parameter']['tuned_parameters']['enc_rnn_layers']
            config['rnnt']['enc_stack_time_factor'] = self.params['model_parameter']['tuned_parameters']['enc_stack_time_factor']
            config['rnnt']['pred_n_hid'] = self.params['model_parameter']['tuned_parameters']['pred_n_hid']
            config['rnnt']['pred_rnn_layers'] = self.params['model_parameter']['tuned_parameters']['pred_rnn_layers']
            config['rnnt']['joint_n_hid'] = self.params['model_parameter']['tuned_parameters']['joint_n_hid']
        with open(config_file, 'w') as f:
            yaml.dump(config, f)