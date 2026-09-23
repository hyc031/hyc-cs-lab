# 一些强化学习内容 主要编写DQN 算法


"""
CartPole-v1 车杆倒立摆 + DQN 完整实现（PyTorch）
================================================================
依赖安装：
    pip install gymnasium torch numpy

运行：
    python cartpole_dqn.py

对应前面讲过的 DQN 要点：
    - 经验回放池 ReplayBuffer：随机采样 mini-batch，打散相邻样本相关性
    - 目标网络 target_net：参数冻结，给出稳定的贝尔曼目标 y
    - ε-greedy：探索与利用平衡，ε 随回合衰减
    - 贝尔曼目标：y = r + γ · max_a' Q(s', a'; θ⁻)，本回合结束时 γ 项置 0
"""
import random
from collections import deque, namedtuple

import gymnasium as gym
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

# ---------------- 超参数 ----------------
ENV_NAME = "CartPole-v1"
GAMMA = 0.99
EPS_START = 1.0
EPS_END = 0.02
EPS_DECAY = 0.995            # 每回合 ε *= 0.995
LR = 1e-3
BATCH_SIZE = 64
BUFFER_CAPACITY = 10_000
MIN_BUFFER = 500             # 经验池攒够这么多样本后再开始学习
TARGET_SYNC_EVERY = 20      # 每 N 个回合同步一次目标网络
NUM_EPISODES = 600
HIDDEN = 64
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

Transition = namedtuple("Transition", ("state", "action", "reward", "next_state", "done"))


class QNet(nn.Module):
    """Q(s, a; θ)：输入状态向量，输出每个动作的 Q 值。"""

    def __init__(self, state_dim: int, n_actions: int, hidden: int = HIDDEN):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(state_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, n_actions),
        )

    def forward(self, x):
        return self.model(x)


class ReplayBuffer:
    """经验回放池：存 (s, a, r, s', done)，随机采样 mini-batch。"""

    def __init__(self, capacity: int):
        self.buffer = deque(maxlen=capacity)

    def push(self, *transition):
        self.buffer.append(Transition(*transition))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        s = np.stack([b.state for b in batch]).astype(np.float32)
        a = np.array([b.action for b in batch], dtype=np.int64)
        r = np.array([b.reward for b in batch], dtype=np.float32)
        ns = np.stack([b.next_state for b in batch]).astype(np.float32)
        d = np.array([b.done for b in batch], dtype=np.float32)
        return s, a, r, ns, d

    def __len__(self):
        return len(self.buffer)


class DQNAgent:
    def __init__(self, state_dim: int, n_actions: int):
        self.n_actions = n_actions
        self.eps = EPS_START
        self.q_net = QNet(state_dim, n_actions).to(DEVICE)         # 评估网络 θ
        self.target_net = QNet(state_dim, n_actions).to(DEVICE)    # 目标网络 θ⁻
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.target_net.eval()
        self.optimizer = optim.Adam(self.q_net.parameters(), lr=LR)
        self.memory = ReplayBuffer(BUFFER_CAPACITY)

    def choose_action(self, state: np.ndarray) -> int:
        """ε-greedy：以 ε 随机探索，否则选 Q 值最大的动作。"""
        if random.random() < self.eps:
            return random.randrange(self.n_actions)
        with torch.no_grad():
            s = torch.as_tensor(state, dtype=torch.float32, device=DEVICE).unsqueeze(0)
            return int(self.q_net(s).argmax(dim=1).item())

    def learn(self):
        """用一个 mini-batch 更新评估网络（核心更新逻辑）。"""
        if len(self.memory) < MIN_BUFFER:
            return
        s, a, r, ns, d = self.memory.sample(BATCH_SIZE)
        s = torch.as_tensor(s, device=DEVICE)
        a = torch.as_tensor(a, device=DEVICE)
        r = torch.as_tensor(r, device=DEVICE)
        ns = torch.as_tensor(ns, device=DEVICE)
        d = torch.as_tensor(d, device=DEVICE)

        # 当前 Q 值：Q(s, a; θ)
        q = self.q_net(s).gather(1, a.unsqueeze(1)).squeeze(1)
        # 贝尔曼目标：y = r + γ · max_a' Q(s', a'; θ⁻)；done=1 时 γ 项为 0
        with torch.no_grad():
            next_q = self.target_net(ns).max(dim=1).values
            y = r + GAMMA * next_q * (1.0 - d)

        loss = F.mse_loss(q, y)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

    def decay_epsilon(self):
        self.eps = max(EPS_END, self.eps * EPS_DECAY)

    def sync_target(self):
        self.target_net.load_state_dict(self.q_net.state_dict())


def main():
    env = gym.make(ENV_NAME)
    agent = DQNAgent(
        state_dim=env.observation_space.shape[0],
        n_actions=env.action_space.n,
    )
    recent_rewards = []

    for episode in range(NUM_EPISODES):
        state, _ = env.reset()
        episode_reward = 0.0
        while True:
            action = agent.choose_action(state)
            next_state, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
            # CartPole 每存活一步 +1；把转移样本存入回放池
            agent.memory.push(state, action, reward, next_state, float(done))
            state = next_state
            episode_reward += reward
            agent.learn()
            if done:
                break

        agent.decay_epsilon()
        if episode % TARGET_SYNC_EVERY == 0:
            agent.sync_target()

        recent_rewards.append(episode_reward)
        if episode % 20 == 0:
            avg = float(np.mean(recent_rewards[-20:]))
            print(f"回合 {episode:4d} | 本回合奖励 {episode_reward:6.1f} | "
                  f"近20回合均值 {avg:6.1f} | ε {agent.eps:.3f}")

    env.close()
    print("训练完成。CartPole-v1 单回合满分 500；连续 100 回合均值 ≥475 视为已解决。")


if __name__ == "__main__":
    main()






