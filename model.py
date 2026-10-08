import torch
import torch.nn as nn
import torch.nn.functional as F

class SpatioTemporalConv3D(nn.Module):
    def __init__(self, in_channels=7, embed_dim=64):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv3d(in_channels, 32, kernel_size=3, padding=1),
            nn.GroupNorm(num_groups=8, num_channels=32),
            nn.GELU(),
            nn.Conv3d(32, embed_dim, kernel_size=3, padding=1),
            nn.BatchNorm3d(embed_dim),
            nn.GELU()
        )

    def forward(self, x):
        x = x.permute(0, 2, 1, 3, 4)
        x = self.conv(x)
        return x

class TemporalWindowAttention(nn.Module):
    def __init__(self, embed_dim=64, num_heads=4, window_size=4):
        super().__init__()
        self.window_size = window_size
        self.attention = nn.MultiheadAttention(embed_dim=embed_dim, num_heads=num_heads, batch_first=True)

    def forward(self, x):
        B, T, D = x.shape
        W = self.window_size
        pad_len = (W - T % W) % W
        if pad_len > 0:
            x = F.pad(x, (0, 0, 0, pad_len))
        Tp = x.shape[1]
        x = x.reshape(B, Tp // W, W, D)
        x = x.reshape(B * (Tp // W), W, D)
        attn_out, _ = self.attention(x, x, x)
        x = x + attn_out
        x = x.reshape(B, Tp, D)
        if pad_len > 0:
            x = x[:, :T]
        return x

class FFTFrequencyGate(nn.Module):
    def __init__(self, embed_dim=64, sequence_length=7):
        super().__init__()
        n_freq = sequence_length // 2 + 1
        self.gate = nn.Parameter(torch.ones(n_freq, embed_dim))

    def forward(self, x):
        in_dtype = x.dtype
        with torch.autocast(device_type="cuda", enabled=False):
            x = x.float()
            freq = torch.fft.rfft(x, dim=1)
            gate = torch.sigmoid(self.gate).unsqueeze(0)
            out = torch.fft.irfft(freq * gate, n=x.shape[1], dim=1)
        return out.to(in_dtype)

class FWinFormerBlock(nn.Module):
    def __init__(self, embed_dim=64, num_heads=4, window_size=4, sequence_length=7):
        super().__init__()
        self.local_cnn = nn.Sequential(
            nn.Conv1d(embed_dim, embed_dim, kernel_size=3, padding=1, groups=embed_dim),
            nn.GELU(),
            nn.Conv1d(embed_dim, embed_dim, kernel_size=1)
        )
        self.window_attention = TemporalWindowAttention(embed_dim, num_heads, window_size)
        self.temporal_mixing = nn.Sequential(
            nn.Conv1d(embed_dim, embed_dim, kernel_size=3, padding=1, groups=embed_dim),
            nn.GELU(),
            nn.Conv1d(embed_dim, embed_dim, kernel_size=1)
        )
        self.fft_gate = FFTFrequencyGate(embed_dim, sequence_length)
        self.norm1 = nn.LayerNorm(embed_dim)
        self.norm2 = nn.LayerNorm(embed_dim)
        self.norm3 = nn.LayerNorm(embed_dim)
        self.norm4 = nn.LayerNorm(embed_dim)

    def forward(self, x):
        residual = x
        x_cnn = x.transpose(1, 2)
        x_cnn = self.local_cnn(x_cnn)
        x_cnn = x_cnn.transpose(1, 2)
        x = self.norm1(residual + x_cnn)

        residual = x
        x_attn = self.window_attention(x)
        x = self.norm2(residual + x_attn)

        residual = x
        x_temp = x.transpose(1, 2)
        x_temp = self.temporal_mixing(x_temp)
        x_temp = x_temp.transpose(1, 2)
        x = self.norm3(residual + x_temp)

        residual = x
        x_fft = self.fft_gate(x)
        x = self.norm4(residual + x_fft)
        return x

class ResidualDepthDecoder(nn.Module):
    def __init__(self, embed_dim=64, n_depths=15, depth_dim=16):
        super().__init__()
        self.n_depths = n_depths
        self.depth_embedding = nn.Parameter(torch.randn(n_depths, depth_dim) * 0.02)
        self.clim_encoder = nn.Sequential(
            nn.Linear(1, 16),
            nn.GELU(),
            nn.Linear(16, 16)
        )
        input_dim = embed_dim + depth_dim + 16
        self.decoder = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.GELU(),
            nn.Dropout(0.10),
            nn.Linear(128, 64),
            nn.GELU(),
            nn.Linear(64, 1)
        )

    def forward(self, ocean_latent, climatology):
        with torch.autocast(device_type="cuda", enabled=False):
            ocean_latent = ocean_latent.float()
            climatology = climatology.float()
            B = ocean_latent.shape[0]

            F_latent = ocean_latent.unsqueeze(1).expand(-1, self.n_depths, -1)
            depth_emb = self.depth_embedding.unsqueeze(0).expand(B, -1, -1)
            clim_emb = self.clim_encoder(climatology.unsqueeze(-1))

            decoder_input = torch.cat([F_latent, depth_emb, clim_emb], dim=-1)
            residual = self.decoder(decoder_input).squeeze(-1)
            temperature = climatology + residual
        return temperature, residual

class ThermoclineAwareOceanModel(nn.Module):
    def __init__(self, in_channels=7, n_depths=15, embed_dim=64, temporal_window=7):
        super().__init__()
        self.st_encoder = SpatioTemporalConv3D(in_channels=in_channels, embed_dim=embed_dim)
        self.fwinformer = FWinFormerBlock(
            embed_dim=embed_dim, num_heads=4, window_size=4, sequence_length=temporal_window
        )
        self.decoder = ResidualDepthDecoder(embed_dim=embed_dim, n_depths=n_depths, depth_dim=16)

    def forward(self, x, climatology):
        features = self.st_encoder(x)
        features = features.mean(dim=(-1, -2))
        features = features.transpose(1, 2)
        temporal_features = self.fwinformer(features)
        ocean_latent = temporal_features.mean(dim=1)
        temperature, residual = self.decoder(ocean_latent, climatology)
        return temperature, residual, ocean_latent