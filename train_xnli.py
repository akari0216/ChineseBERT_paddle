#encoding=utf8
# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import json
import time 
import os
import numpy as np
import random
from functools import partial
import paddle.nn.functional as F
from paddlenlp.data import Stack, Tuple, Pad, Dict

import paddle
import sys
from paddle.nn import functional as F

from paddle.nn.layer import CrossEntropyLoss


from paddle.io import DataLoader

from paddlenlp.transformers import LinearDecayWithWarmup
from pdchinesebert.modeling import ChineseBertForSequenceClassification
from pdchinesebert.tokenizer import ChineseBertTokenizer

from paddlenlp.datasets import load_dataset

import random
import paddle
import numpy as np
from utils import set_seed


parser = argparse.ArgumentParser()
parser.add_argument("--save_dir", default='outputs/xnli', type=str, help="The output directory where the model checkpoints will be written.")
parser.add_argument("--max_seq_length", default=256, type=int, help="The maximum total input sequence length after tokenization. "
    "Sequences longer than this will be truncated, sequences shorter will be padded.")
parser.add_argument("--batch_size", default=32, type=int, help="Batch size per GPU/CPU for training.")
parser.add_argument("--learning_rate", default=1.5e-5, type=float, help="The initial learning rate for Adam.")
parser.add_argument("--weight_decay", default=0.0001, type=float, help="Weight decay if we apply some.")
parser.add_argument("--epochs", default=5, type=int, help="Total number of training epochs to perform.")
parser.add_argument("--warmup_proportion", default=0.1, type=float, help="Linear warmup proption over the training process.")
parser.add_argument("--init_from_ckpt", type=str, default=None, help="The path of checkpoint to be loaded.")
parser.add_argument("--seed", type=int, default=2333, help="random seed for initialization")
parser.add_argument("--device", choices=["cpu", "gpu", "xpu"], default="gpu", help="Select which device to train model, defaults to gpu.")
parser.add_argument("--data_path", type=str, default="./data/XNLI", help="The path of datasets to be loaded")
parser.add_argument("--adam_epsilon", default=1e-8, type=float, help="Epsilon for Adam optimizer.")
args = parser.parse_args()

paddle.set_device(args.device)
set_seed(args.seed)

from utils import load_ds_xnli

data_dir = args.data_path
train_path = os.path.join(data_dir,"train.tsv")
dev_path = os.path.join(data_dir,"dev.tsv")
test_path = os.path.join(data_dir,"test.tsv")

train_ds, dev_ds, test_ds= load_ds_xnli(datafiles=[train_path, dev_path,test_path])
model = ChineseBertForSequenceClassification.from_pretrained("ChineseBERT-large",num_classes=3)
tokenizer = ChineseBertTokenizer.from_pretrained("ChineseBERT-large")  

print(" | load pretrained model state sucessfully.")
# model = paddle.DataParallel(model)
idx = 1
def convert_example(example, tokenizer, max_seq_length=512, is_test=False):
    # global idx
    # print(idx, example)
    # idx = idx + 1
    
    label_map = {"contradictory":0,"contradiction":0,"entailment":2,"neutral":1}
    first, second, third = example['sentence1'], example['sentence2'], example['label']

    encoded_inputs = tokenizer(first,second,max_seq_len=max_seq_length)
    input_ids = encoded_inputs["input_ids"]
    pinyin_ids = encoded_inputs["pinyin_ids"]
    
    label = np.array([label_map[third]], dtype="int64")
    assert len(input_ids) <= max_seq_length
    return input_ids, pinyin_ids, label


# # 批量数据大小
# batch_size = 32
# # 文本序列最大长度
# max_seq_length = 256

# 将数据处理成模型可读入的数据格式
trans_func = partial(
    convert_example,
    tokenizer=tokenizer,
    max_seq_length=args.max_seq_length)

# 将数据组成批量式数据，如
# 将不同长度的文本序列padding到批量式数据中最大长度
# 将每条数据label堆叠在一起

batchify_fn = lambda samples, fn=Tuple(
    Pad(axis=0, pad_val=tokenizer.pad_token_id), # input_ids
    # Pad(axis=0, pad_val=tokenizer.pad_token_type_id), # token_type_ids
    Pad(axis=0, pad_val=0), # pinyin_ids
    Stack()  # labels
): [data for data in fn(samples)]

# batchify_fn = lambda samples, fn=Dict(
#     "input_ids":Pad(axis=0, pad_val=tokenizer.pad_token_id), # input_ids
#     "pinyin_ids":Pad(axis=0, pad_val=0),                     # pinyin_ids
#     "labels":Stack(dtype="int64")                            # labels
# ): fn(samples)


from utils import create_dataloader
# from utils import get_dataloader

train_data_loader = create_dataloader(
    train_ds,
    mode='train',
    batch_size=args.batch_size,
    batchify_fn=batchify_fn,
    trans_fn=trans_func
    )

dev_data_loader = create_dataloader(
    dev_ds,
    mode='dev',
    batch_size=args.batch_size,
    batchify_fn=batchify_fn,
    trans_fn=trans_func)

test_data_loader = create_dataloader(
    test_ds,
    mode='test',
    batch_size=args.batch_size,
    batchify_fn=batchify_fn,
    trans_fn=trans_func)


from utils import evaluate


num_training_steps = len(train_data_loader) * args.epochs

lr_scheduler = LinearDecayWithWarmup(args.learning_rate, 
    num_training_steps, args.warmup_proportion)

# Generate parameter names needed to perform weight decay.
# All bias and LayerNorm parameters are excluded.
decay_params = [
    p.name for n, p in model.named_parameters()
    if not any(nd in n for nd in ["bias", "norm"])
]

optimizer = paddle.optimizer.AdamW(
    beta1=0.9, beta2=0.98, 
    learning_rate=lr_scheduler,
    epsilon= args.adam_epsilon,
    parameters=model.parameters(),
    weight_decay=args.weight_decay,
    apply_decay_param_fun=lambda x: x in decay_params)

# # # 训练轮次
# epochs = 5
# # 训练过程中保存模型参数的文件夹
# ckpt_dir = "XNLI_ckpt"
# # len(train_data_loader)一轮训练所需要的step数
# num_training_steps = len(train_data_loader) * epochs

# # Adam优化器
# optimizer = paddle.optimizer.AdamW(
#     beta1=0.9, beta2=0.98, 
#     learning_rate=2e-5,
#     parameters= model.parameters())
# 交叉熵损失函数
criterion = paddle.nn.loss.CrossEntropyLoss()
# accuracy评价指标
metric = paddle.metric.Accuracy()
print(args)
# 开启训练
global_step = 0
tic_train = time.time()
for epoch in range(1, args.epochs + 1):
    for step, batch in enumerate(train_data_loader, start=1):
        # print(batch)
        input_ids, pinyin_ids, labels = batch
        # print(input_ids.shape)
        batch_size, length = input_ids.shape
        # 喂数据给model
        #print(batch)
        pinyin_ids = paddle.reshape(pinyin_ids, [batch_size, length, 8])
        logits = model(input_ids, pinyin_ids)
        # 计算损失函数值
        loss = criterion(logits, labels)
        # 预测分类概率值
        probs = F.softmax(logits, axis=1)
        # 计算acc
        correct = metric.compute(probs, labels)
        metric.update(correct)
        acc = metric.accumulate()


        global_step += 1
        if global_step % 10 == 0:
            print(
                "global step %d, epoch: %d, batch: %d, loss: %.5f, accu: %.5f, speed: %.2f step/s"
                % (global_step, epoch, step, loss, acc,
                    10 / (time.time() - tic_train)))
            tic_train = time.time()
        
        # 反向梯度回传，更新参数
        loss.backward()
        optimizer.step()
        lr_scheduler.step()
        optimizer.clear_grad()

        if global_step % 100 == 0:
            
            # 评估当前训练的模型
            dev_acc = evaluate(model, criterion, metric, dev_data_loader)
            test_acc = evaluate(model, criterion, metric, test_data_loader)
            if test_acc >= 0.816:
                save_dir = os.path.join(args.save_dir, "model_%d" % global_step)
                if not os.path.exists(save_dir):
                    os.makedirs(save_dir)
                    # sys.exit(0)
                    # 保存当前模型参数等
                    model.save_pretrained(save_dir)
                    # 保存tokenizer的词表等
                    tokenizer.save_pretrained(save_dir)






