# EVM Multi-to-Multi Transfer Tool

EVM 多转多工具 — 批量转账原生代币/ERC20/ERC721，支持所有 EVM 链。

## 功能

- 支持多钱包批量转账（原生代币、ERC20、ERC721 NFT）
- 预配置 13+ 主流 EVM 网络（Ethereum、BSC、Polygon、Arbitrum、Base 等）
- 支持自定义 RPC 和链 ID
- 自动检测 EIP-1559 / Legacy gas 模式，自适应不同链
- Gas 价格和 Gas Limit 自动估算，带 20% buffer 防止交易失败
- 支持全部转出、指定数量转出、保留余额等模式
- 实时余额查询、转账进度显示、交易日志

## 截图

![UI](https://img.shields.io/badge/UI-CustomTkinter-blue)

## 安装

```bash
pip install web3 customtkinter
```

## 使用

1. 准备钱包文件（txt 格式），每行格式：
   ```
   发送地址----私钥----接收地址
   ```

2. 运行程序：
   ```bash
   python evm_transfer.py
   ```

3. 选择网络 → 连接 → 导入钱包文件 → 查询余额 → 开始转账

## 支持的网络

| 网络 | 链 ID | 原生代币 |
|------|--------|----------|
| Ethereum | 1 | ETH |
| BSC | 56 | BNB |
| Polygon | 137 | MATIC |
| Arbitrum | 42161 | ETH |
| Optimism | 10 | ETH |
| Avalanche | 43114 | AVAX |
| Base | 8453 | ETH |
| Fantom | 250 | FTM |
| zkSync Era | 324 | ETH |
| Linea | 59144 | ETH |
| Scroll | 534352 | ETH |
| Mantle | 5000 | MNT |
| Sepolia 测试网 | 11155111 | ETH |

也支持通过自定义 RPC 连接任意 EVM 兼容链。

## Gas 机制

- 自动检测链是否支持 EIP-1559
- EIP-1559 链：使用 `maxFeePerGas = baseFee × 2 + priorityFee`
- Legacy 链：使用 `gasPrice × 1.2` 作为 buffer
- Gas Limit 通过 `eth_estimateGas` 动态估算，加 20% 余量

## 注意事项

- 请妥善保管私钥文件，不要泄露
- 建议先用测试网（Sepolia）验证流程
- 转账前请确认网络、合约地址、数量等参数正确

## License

MIT
