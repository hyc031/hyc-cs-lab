# --- 导包
import torch

import torch.nn as nn
import torch.nn.functional as F
import math

# ---
X = torch.randn(1, 1024, 512) # bsz, seq_len, d_model
print(X.shape)

# 设置一些相关参数
d_model = 512
n_head = 8  # 多头注意力 的数量
d_k = d_model // n_head


# 
class MHA(nn.Module):
    def __init__(self, d_model, n_head) -> None:
        super(MHA, self).__init__()

        self.n_head = n_head
        self.d_model = d_model
        self.w_q = nn.Linear(d_model, d_model)
        self.w_k = nn.Linear(d_model, d_model)
        self.w_v = nn.Linear(d_model, d_model)
        self.w_o = nn.Linear(d_model, d_model)
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, q, k, v):
        bsz, seq_len, d_model = q.shape
        n_d = self.d_model // self.n_head
        # 线性变换
        q, k, v = self.w_q(q), self.w_k(k), self.w_v(v)

        q = q.view(bsz, seq_len, self.n_head, n_d).transpose(1, 2)  # bsz, n_head, seq_len, n_d
        k = k.view(bsz, seq_len, self.n_head, n_d).transpose(1, 2)  # bsz, n_head, seq_len, n_d
        v = v.view(bsz, seq_len, self.n_head, n_d).transpose(1, 2)  # bsz, n_head, seq_len, n_d

        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(n_d)  # bsz, n_head, seq_len, seq_len
        mask = torch.tril(torch.ones(seq_len, seq_len)).to(q.device)  # 下三角矩阵
        scores = scores.masked_fill(mask == 0, float('-inf'))  # bsz, n_head, seq_len, seq_len
        attn = self.softmax(scores)  # bsz, n_head, seq_len, seq_len
        out = torch.matmul(attn, v)  # bsz, n_head, seq_len, n_d
        out = out.transpose(1, 2).contiguous().view(bsz, seq_len, self.d_model)  # bsz, seq_len, d_model
        out = self.w_o(out)  # bsz, seq_len, d_model
        return out


attention = MHA(d_model, n_head)
x_o = attention(X, X, X)
print(x_o)  # torch.Size([2, 1024, 512])









