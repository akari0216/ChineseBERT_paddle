from datasets.bert_dataset import BertDataset
from models1.modeling_glycebert import GlyceBertModel

tokenizer = BertDataset("./ChineseBERT-base")
chinese_bert = GlyceBertModel.from_pretrained("./ChineseBERT-base")
sentence = '欢迎使用paddle'

input_ids, pinyin_ids = tokenizer.tokenize_sentence(sentence)
length = input_ids.shape[0]
input_ids = input_ids.view(1, length)
pinyin_ids = pinyin_ids.view(1, length, 8)
output_hidden = chinese_bert.forward(input_ids, pinyin_ids)[0]
torch_array = output_hidden.cpu().detach().numpy()
print("torch_prediction_logits shape:{}".format(torch_array.shape))
print("torch_prediction_logits:{}".format(torch_array))
# print(output_hidden.shape)
# print(output_hidden)

import paddle
import paddlenlp
import numpy as np
from models.modeling import GlyceBertModel

paddle_model_name = "ChineseBERT-base"


# paddle_model = BertForPretraining.from_pretrained(paddle_model_name)
paddle_model = GlyceBertModel.from_pretrained(paddle_model_name)



from datasets.bert_dataset1 import BertDataset



tokenizer = BertDataset("E:/ChineseBERT/ChineseBERT_paddle/ChineseBERT-base")

sentence = '欢迎使用paddle'

input_ids, pinyin_ids = tokenizer.tokenize_sentence(sentence)
length = input_ids.shape[0]

input_ids = paddle.reshape(input_ids,[1,length])
pinyin_ids = paddle.reshape(pinyin_ids,[1, length, 8])

paddle_model.eval()

# print(paddle_model)



# paddle_inputs = paddle_tokenizer(text)
# paddle_inputs = {k:paddle.to_tensor([v]) for (k, v) in paddle_inputs.items()}
# # print(paddle_inputs)
paddle_outputs = paddle_model(input_ids,pinyin_ids)

paddle_logits = paddle_outputs[0]
paddle_array = paddle_logits.numpy()
print("paddle_prediction_logits shape:{}".format(paddle_array.shape))
print("paddle_prediction_logits:{}".format(paddle_array))


# the output logits should have the same shape
assert torch_array.shape == paddle_array.shape, "the output logits should have the same shape, but got : {} and {} instead".format(torch_array.shape, paddle_array.shape)
diff = torch_array - paddle_array
print(np.amax(abs(diff)))

