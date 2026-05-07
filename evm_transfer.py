#!/usr/bin/env python3
"""EVM 多转多工具 — 批量转账原生代币/ERC20/ERC721，支持所有EVM链。"""

import json
import threading
import time
import tkinter as tk
from datetime import datetime
from decimal import Decimal
from tkinter import filedialog, messagebox

import customtkinter as ctk
from web3 import Web3
from web3.exceptions import ContractLogicError

# ── 主题 ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── ABI ──────────────────────────────────────────────────────────────────────
ERC20_ABI = json.loads("""[
  {"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
  {"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},
  {"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"},
  {"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"}
]""")

ERC721_ABI = json.loads("""[
  {"constant":true,"inputs":[{"name":"tokenId","type":"uint256"}],"name":"ownerOf","outputs":[{"name":"","type":"address"}],"type":"function"},
  {"constant":false,"inputs":[{"name":"from","type":"address"},{"name":"to","type":"address"},{"name":"tokenId","type":"uint256"}],"name":"transferFrom","outputs":[],"type":"function"},
  {"constant":false,"inputs":[{"name":"from","type":"address"},{"name":"to","type":"address"},{"name":"tokenId","type":"uint256"}],"name":"safeTransferFrom","outputs":[],"type":"function"},
  {"constant":true,"inputs":[{"name":"owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"}
]""")

# ── 预配置网络 ────────────────────────────────────────────────────────────────
NETWORKS = {
    "Ethereum": {"rpc": "https://eth.llamarpc.com", "chain_id": 1, "symbol": "ETH", "explorer": "https://etherscan.io/tx/"},
    "BSC": {"rpc": "https://bsc-dataseed1.binance.org", "chain_id": 56, "symbol": "BNB", "explorer": "https://bscscan.com/tx/"},
    "Polygon": {"rpc": "https://polygon-rpc.com", "chain_id": 137, "symbol": "MATIC", "explorer": "https://polygonscan.com/tx/"},
    "Arbitrum": {"rpc": "https://arb1.arbitrum.io/rpc", "chain_id": 42161, "symbol": "ETH", "explorer": "https://arbiscan.io/tx/"},
    "Optimism": {"rpc": "https://mainnet.optimism.io", "chain_id": 10, "symbol": "ETH", "explorer": "https://optimistic.etherscan.io/tx/"},
    "Avalanche": {"rpc": "https://api.avax.network/ext/bc/C/rpc", "chain_id": 43114, "symbol": "AVAX", "explorer": "https://snowtrace.io/tx/"},
    "Base": {"rpc": "https://mainnet.base.org", "chain_id": 8453, "symbol": "ETH", "explorer": "https://basescan.org/tx/"},
    "Fantom": {"rpc": "https://rpc.ftm.tools", "chain_id": 250, "symbol": "FTM", "explorer": "https://ftmscan.com/tx/"},
    "zkSync Era": {"rpc": "https://mainnet.era.zksync.io", "chain_id": 324, "symbol": "ETH", "explorer": "https://explorer.zksync.io/tx/"},
    "Linea": {"rpc": "https://rpc.linea.build", "chain_id": 59144, "symbol": "ETH", "explorer": "https://lineascan.build/tx/"},
    "Scroll": {"rpc": "https://rpc.scroll.io", "chain_id": 534352, "symbol": "ETH", "explorer": "https://scrollscan.com/tx/"},
    "Mantle": {"rpc": "https://rpc.mantle.xyz", "chain_id": 5000, "symbol": "MNT", "explorer": "https://explorer.mantle.xyz/tx/"},
    "Sepolia (测试网)": {"rpc": "https://rpc.sepolia.org", "chain_id": 11155111, "symbol": "ETH", "explorer": "https://sepolia.etherscan.io/tx/"},
    "自定义": {"rpc": "", "chain_id": 0, "symbol": "ETH", "explorer": ""},
}

# ── 状态中文映射 ──────────────────────────────────────────────────────────────
STATUS_TEXT = {
    "Ready": "就绪", "Success": "成功", "Failed": "失败",
    "Pending": "发送中", "Querying": "查询中", "Skipped": "已跳过",
}
STATUS_COLOR = {
    "Ready": "#A0AEC0", "Success": "#48BB78", "Failed": "#F56565",
    "Pending": "#ECC94B", "Querying": "#63B3ED", "Skipped": "#ED8936",
}

# ── 钱包数据 ──────────────────────────────────────────────────────────────────
class WalletEntry:
    __slots__ = ("address", "private_key", "to_address", "balance", "token_balance", "status", "tx_hash")

    def __init__(self, address: str, private_key: str, to_address: str):
        self.address = Web3.to_checksum_address(address.strip())
        self.private_key = private_key.strip()
        self.to_address = Web3.to_checksum_address(to_address.strip())
        self.balance = ""
        self.token_balance = ""
        self.status = "Ready"
        self.tx_hash = ""


# ── 可滚动表格 ────────────────────────────────────────────────────────────────
class WalletTable(ctk.CTkScrollableFrame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.rows: list[list[ctk.CTkLabel]] = []
        headers = ["#", "发送地址", "接收地址", "余额", "状态"]
        for c, h in enumerate(headers):
            lbl = ctk.CTkLabel(self, text=h, font=ctk.CTkFont(size=13, weight="bold"),
                               text_color="#8B95A5")
            lbl.grid(row=0, column=c, padx=6, pady=(4, 8), sticky="w")

    def clear(self):
        for row in self.rows:
            for lbl in row:
                lbl.destroy()
        self.rows.clear()

    def add_row(self, idx: int, wallet: WalletEntry):
        r = idx + 1
        short_from = wallet.address[:6] + "..." + wallet.address[-4:]
        short_to = wallet.to_address[:6] + "..." + wallet.to_address[-4:]
        bal = wallet.balance or "—"
        status_cn = STATUS_TEXT.get(wallet.status, wallet.status)
        sc = STATUS_COLOR.get(wallet.status, "#A0AEC0")
        cells = []
        for c, txt in enumerate([str(r), short_from, short_to, bal, status_cn]):
            tc = sc if c == 4 else "#E2E8F0"
            lbl = ctk.CTkLabel(self, text=txt, font=ctk.CTkFont(size=12),
                               text_color=tc, anchor="w")
            lbl.grid(row=r, column=c, padx=6, pady=2, sticky="w")
            cells.append(lbl)
        self.rows.append(cells)

    def update_row(self, idx: int, wallet: WalletEntry):
        if idx >= len(self.rows):
            return
        row = self.rows[idx]
        bal = wallet.balance or "—"
        status_cn = STATUS_TEXT.get(wallet.status, wallet.status)
        sc = STATUS_COLOR.get(wallet.status, "#A0AEC0")
        row[3].configure(text=bal)
        row[4].configure(text=status_cn, text_color=sc)


# ── 主应用 ────────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("EVM 多转多工具")
        self.geometry("1100x750")
        self.minsize(900, 600)

        self.wallets: list[WalletEntry] = []
        self.w3: Web3 | None = None
        self.running = False

        self._build_ui()

    # ── 构建界面 ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ═══ 侧边栏 ═══
        sidebar = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color="#1A1D23")
        sidebar.grid(row=0, column=0, sticky="nswe")
        sidebar.grid_rowconfigure(10, weight=1)

        logo = ctk.CTkLabel(sidebar, text="  EVM 多转多", font=ctk.CTkFont(size=20, weight="bold"),
                            text_color="#60A5FA")
        logo.grid(row=0, column=0, padx=20, pady=(28, 4), sticky="w")
        sub = ctk.CTkLabel(sidebar, text="  多钱包批量转账工具",
                           font=ctk.CTkFont(size=11), text_color="#6B7280")
        sub.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        ctk.CTkFrame(sidebar, height=1, fg_color="#2D3748").grid(row=2, column=0, padx=16, sticky="we", pady=4)

        section_font = ctk.CTkFont(size=11, weight="bold")

        ctk.CTkLabel(sidebar, text="选择网络", font=section_font, text_color="#4A5568"
                     ).grid(row=3, column=0, padx=20, pady=(16, 4), sticky="w")

        self.network_var = ctk.StringVar(value="Ethereum")
        self.network_menu = ctk.CTkOptionMenu(
            sidebar, values=list(NETWORKS.keys()), variable=self.network_var,
            command=self._on_network_change, width=170,
            fg_color="#2D3748", button_color="#3B82F6", button_hover_color="#2563EB")
        self.network_menu.grid(row=4, column=0, padx=20, pady=4, sticky="w")

        ctk.CTkLabel(sidebar, text="RPC 地址", font=section_font, text_color="#4A5568"
                     ).grid(row=5, column=0, padx=20, pady=(12, 4), sticky="w")
        self.rpc_entry = ctk.CTkEntry(sidebar, width=170, placeholder_text="https://...",
                                      fg_color="#2D3748", border_color="#4A5568")
        self.rpc_entry.grid(row=6, column=0, padx=20, pady=4, sticky="w")
        self.rpc_entry.insert(0, NETWORKS["Ethereum"]["rpc"])

        ctk.CTkLabel(sidebar, text="链 ID", font=section_font, text_color="#4A5568"
                     ).grid(row=7, column=0, padx=20, pady=(12, 4), sticky="w")
        self.chain_id_entry = ctk.CTkEntry(sidebar, width=170, fg_color="#2D3748", border_color="#4A5568")
        self.chain_id_entry.grid(row=8, column=0, padx=20, pady=4, sticky="w")
        self.chain_id_entry.insert(0, "1")

        self.connect_btn = ctk.CTkButton(sidebar, text="连接网络", width=170,
                                         fg_color="#3B82F6", hover_color="#2563EB",
                                         command=self._connect_rpc)
        self.connect_btn.grid(row=9, column=0, padx=20, pady=(12, 4), sticky="w")

        self.conn_status = ctk.CTkLabel(sidebar, text="未连接",
                                        font=ctk.CTkFont(size=11), text_color="#F56565")
        self.conn_status.grid(row=10, column=0, padx=20, pady=(2, 20), sticky="nw")

        # ═══ 主区域 ═══
        main = ctk.CTkFrame(self, fg_color="#111318", corner_radius=0)
        main.grid(row=0, column=1, sticky="nswe")
        main.grid_rowconfigure(4, weight=1)
        main.grid_rowconfigure(6, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # ─── 导入栏 ───
        import_frame = ctk.CTkFrame(main, fg_color="#1A1D23", corner_radius=10)
        import_frame.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="we")
        import_frame.grid_columnconfigure(1, weight=1)

        self.load_btn = ctk.CTkButton(import_frame, text="导入文件", width=100,
                                      fg_color="#3B82F6", hover_color="#2563EB",
                                      command=self._load_file)
        self.load_btn.grid(row=0, column=0, padx=(12, 8), pady=10)

        self.file_label = ctk.CTkLabel(import_frame, text="未加载文件  (格式: 地址----私钥----目标地址)",
                                       font=ctk.CTkFont(size=12), text_color="#6B7280", anchor="w")
        self.file_label.grid(row=0, column=1, padx=4, pady=10, sticky="w")

        self.wallet_count_lbl = ctk.CTkLabel(import_frame, text="",
                                             font=ctk.CTkFont(size=12, weight="bold"),
                                             text_color="#48BB78")
        self.wallet_count_lbl.grid(row=0, column=2, padx=(4, 16), pady=10, sticky="e")

        # ─── 转账配置 ───
        config_frame = ctk.CTkFrame(main, fg_color="#1A1D23", corner_radius=10)
        config_frame.grid(row=1, column=0, padx=16, pady=6, sticky="we")
        config_frame.grid_columnconfigure(2, weight=1)

        # 转账类型
        ctk.CTkLabel(config_frame, text="转账类型", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8B95A5").grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self.transfer_type = ctk.StringVar(value="Native")
        type_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        type_frame.grid(row=0, column=1, columnspan=5, padx=8, pady=(10, 4), sticky="w")
        for i, (val, label) in enumerate([("Native", "原生代币"), ("ERC20", "ERC20 代币"), ("ERC721", "ERC721 NFT")]):
            ctk.CTkRadioButton(type_frame, text=label, variable=self.transfer_type, value=val,
                               command=self._on_type_change, fg_color="#3B82F6",
                               border_color="#4A5568", hover_color="#2563EB"
                               ).grid(row=0, column=i, padx=(0, 16))

        # 合约地址
        ctk.CTkLabel(config_frame, text="合约地址", font=ctk.CTkFont(size=12),
                     text_color="#8B95A5").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self.contract_entry = ctk.CTkEntry(config_frame, placeholder_text="0x... (ERC20/ERC721 合约地址)",
                                           fg_color="#2D3748", border_color="#4A5568")
        self.contract_entry.grid(row=1, column=1, columnspan=5, padx=(8, 16), pady=4, sticky="we")
        self.contract_entry.configure(state="disabled")

        # 数量 / 保留
        ctk.CTkLabel(config_frame, text="转账数量", font=ctk.CTkFont(size=12),
                     text_color="#8B95A5").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self.amount_entry = ctk.CTkEntry(config_frame, width=140, placeholder_text="0 = 全部转出",
                                         fg_color="#2D3748", border_color="#4A5568")
        self.amount_entry.grid(row=2, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(config_frame, text="保留数量", font=ctk.CTkFont(size=12),
                     text_color="#8B95A5").grid(row=2, column=2, padx=(16, 4), pady=4, sticky="e")
        self.reserve_entry = ctk.CTkEntry(config_frame, width=120, placeholder_text="0",
                                          fg_color="#2D3748", border_color="#4A5568")
        self.reserve_entry.grid(row=2, column=3, padx=8, pady=4, sticky="w")

        # ERC721 Token ID
        self.token_id_label = ctk.CTkLabel(config_frame, text="Token ID", font=ctk.CTkFont(size=12),
                                            text_color="#8B95A5")
        self.token_id_entry = ctk.CTkEntry(config_frame, width=200,
                                           placeholder_text="1,2,3 (逗号分隔)",
                                           fg_color="#2D3748", border_color="#4A5568")

        # Gas 设置
        ctk.CTkLabel(config_frame, text="Gas 价格", font=ctk.CTkFont(size=12),
                     text_color="#8B95A5").grid(row=3, column=0, padx=12, pady=4, sticky="w")
        gas_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        gas_frame.grid(row=3, column=1, columnspan=5, padx=8, pady=4, sticky="w")

        self.gas_auto = ctk.BooleanVar(value=True)
        self.gas_check = ctk.CTkCheckBox(gas_frame, text="自动", variable=self.gas_auto,
                                         command=self._on_gas_toggle, fg_color="#3B82F6",
                                         border_color="#4A5568", hover_color="#2563EB")
        self.gas_check.grid(row=0, column=0, padx=(0, 12))

        self.gas_entry = ctk.CTkEntry(gas_frame, width=100, placeholder_text="Gwei",
                                      fg_color="#2D3748", border_color="#4A5568", state="disabled")
        self.gas_entry.grid(row=0, column=1, padx=4)

        ctk.CTkLabel(gas_frame, text="Gas 上限:", font=ctk.CTkFont(size=12),
                     text_color="#8B95A5").grid(row=0, column=2, padx=(20, 4))
        self.gaslimit_entry = ctk.CTkEntry(gas_frame, width=100, placeholder_text="自动",
                                           fg_color="#2D3748", border_color="#4A5568")
        self.gaslimit_entry.grid(row=0, column=3, padx=4)

        # 交易间隔
        ctk.CTkLabel(config_frame, text="间隔(秒)", font=ctk.CTkFont(size=12),
                     text_color="#8B95A5").grid(row=4, column=0, padx=12, pady=(4, 10), sticky="w")
        self.delay_entry = ctk.CTkEntry(config_frame, width=80, placeholder_text="1",
                                        fg_color="#2D3748", border_color="#4A5568")
        self.delay_entry.insert(0, "1")
        self.delay_entry.grid(row=4, column=1, padx=8, pady=(4, 10), sticky="w")

        # ─── 操作按钮 ───
        action_frame = ctk.CTkFrame(main, fg_color="transparent")
        action_frame.grid(row=2, column=0, padx=16, pady=6, sticky="we")

        self.query_btn = ctk.CTkButton(action_frame, text="查询余额", width=130,
                                       fg_color="#2D3748", hover_color="#4A5568",
                                       border_width=1, border_color="#4A5568",
                                       command=self._query_balances)
        self.query_btn.pack(side="left", padx=(0, 8))

        self.start_btn = ctk.CTkButton(action_frame, text="开始转账", width=130,
                                       fg_color="#10B981", hover_color="#059669",
                                       command=self._start_transfer)
        self.start_btn.pack(side="left", padx=8)

        self.stop_btn = ctk.CTkButton(action_frame, text="停止", width=80,
                                      fg_color="#EF4444", hover_color="#DC2626",
                                      command=self._stop_transfer, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        self.progress = ctk.CTkProgressBar(action_frame, width=200, progress_color="#3B82F6")
        self.progress.pack(side="right", padx=(8, 0))
        self.progress.set(0)

        # ─── 分隔线 ───
        ctk.CTkFrame(main, height=1, fg_color="#2D3748").grid(row=3, column=0, padx=16, sticky="we", pady=4)

        # ─── 钱包表格 ───
        self.table = WalletTable(main, fg_color="#1A1D23", corner_radius=10)
        self.table.grid(row=4, column=0, padx=16, pady=6, sticky="nswe")

        # ─── 分隔线 ───
        ctk.CTkFrame(main, height=1, fg_color="#2D3748").grid(row=5, column=0, padx=16, sticky="we", pady=4)

        # ─── 日志区域 ───
        self.log_box = ctk.CTkTextbox(main, fg_color="#1A1D23", corner_radius=10,
                                      font=ctk.CTkFont(family="Consolas", size=11),
                                      text_color="#A0AEC0", state="disabled")
        self.log_box.grid(row=6, column=0, padx=16, pady=(6, 12), sticky="nswe")

    # ── 网络切换 ──────────────────────────────────────────────────────────────
    def _on_network_change(self, name: str):
        net = NETWORKS[name]
        self.rpc_entry.delete(0, "end")
        self.rpc_entry.insert(0, net["rpc"])
        self.chain_id_entry.delete(0, "end")
        self.chain_id_entry.insert(0, str(net["chain_id"]))
        if name != "自定义":
            self._connect_rpc()

    def _connect_rpc(self):
        rpc = self.rpc_entry.get().strip()
        if not rpc:
            self.conn_status.configure(text="请输入 RPC 地址", text_color="#F56565")
            return
        try:
            self.w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
            if self.w3.is_connected():
                cid = self.w3.eth.chain_id
                self.chain_id_entry.delete(0, "end")
                self.chain_id_entry.insert(0, str(cid))
                net_name = self.network_var.get()
                sym = NETWORKS.get(net_name, {}).get("symbol", "ETH")
                self.conn_status.configure(text=f"已连接  链 {cid} ({sym})", text_color="#48BB78")
                self._log(f"已连接 {net_name} (链 ID: {cid})")
            else:
                self.conn_status.configure(text="连接失败", text_color="#F56565")
        except Exception as e:
            self.conn_status.configure(text="连接错误", text_color="#F56565")
            self._log(f"RPC 错误: {e}")

    # ── 导入文件 ──────────────────────────────────────────────────────────────
    def _load_file(self):
        path = filedialog.askopenfilename(
            title="选择钱包文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        self.wallets.clear()
        errors = 0
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("----")
                if len(parts) < 3:
                    self._log(f"第 {lineno} 行: 格式错误 (需要 地址----私钥----目标地址)")
                    errors += 1
                    continue
                try:
                    w = WalletEntry(parts[0], parts[1], parts[2])
                    self.wallets.append(w)
                except Exception as e:
                    self._log(f"第 {lineno} 行: {e}")
                    errors += 1

        self._refresh_table()
        fname = path.replace("\\", "/").split("/")[-1]
        self.file_label.configure(text=fname)
        self.wallet_count_lbl.configure(text=f"已加载 {len(self.wallets)} 个钱包")
        if errors:
            self._log(f"已加载 {len(self.wallets)} 个钱包 ({errors} 个错误)")
        else:
            self._log(f"已加载 {len(self.wallets)} 个钱包")

    # ── 表格刷新 ──────────────────────────────────────────────────────────────
    def _refresh_table(self):
        self.table.clear()
        for i, w in enumerate(self.wallets):
            self.table.add_row(i, w)

    def _update_table_row(self, idx: int):
        self.table.update_row(idx, self.wallets[idx])

    # ── 类型切换 ──────────────────────────────────────────────────────────────
    def _on_type_change(self):
        t = self.transfer_type.get()
        if t == "Native":
            self.contract_entry.configure(state="disabled")
            self.amount_entry.grid()
            self.reserve_entry.grid()
            self.token_id_label.grid_remove()
            self.token_id_entry.grid_remove()
        elif t == "ERC20":
            self.contract_entry.configure(state="normal")
            self.amount_entry.grid()
            self.reserve_entry.grid()
            self.token_id_label.grid_remove()
            self.token_id_entry.grid_remove()
        else:  # ERC721
            self.contract_entry.configure(state="normal")
            self.amount_entry.grid_remove()
            self.reserve_entry.grid_remove()
            self.token_id_label.grid(row=2, column=2, padx=(16, 4), pady=4, sticky="e")
            self.token_id_entry.grid(row=2, column=3, padx=8, pady=4, sticky="w")

    def _on_gas_toggle(self):
        if self.gas_auto.get():
            self.gas_entry.configure(state="disabled")
        else:
            self.gas_entry.configure(state="normal")

    # ── 日志 ──────────────────────────────────────────────────────────────────
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ── 查询余额 ──────────────────────────────────────────────────────────────
    def _query_balances(self):
        if not self.w3 or not self.w3.is_connected():
            messagebox.showwarning("未连接", "请先连接 RPC 网络。")
            return
        if not self.wallets:
            messagebox.showinfo("无钱包", "请先导入钱包文件。")
            return
        threading.Thread(target=self._query_thread, daemon=True).start()

    def _query_thread(self):
        self._log("正在查询余额...")
        t = self.transfer_type.get()
        contract = None
        decimals = 18
        symbol = NETWORKS.get(self.network_var.get(), {}).get("symbol", "ETH")

        if t == "ERC20":
            addr = self.contract_entry.get().strip()
            if not addr:
                self._log("请输入 ERC20 合约地址")
                return
            try:
                contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(addr), abi=ERC20_ABI)
                decimals = contract.functions.decimals().call()
                symbol = contract.functions.symbol().call()
                self._log(f"代币: {symbol}, 精度: {decimals}")
            except Exception as e:
                self._log(f"合约错误: {e}")
                return
        elif t == "ERC721":
            addr = self.contract_entry.get().strip()
            if not addr:
                self._log("请输入 ERC721 合约地址")
                return
            try:
                contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(addr), abi=ERC721_ABI)
                symbol = contract.functions.symbol().call()
                self._log(f"NFT 合集: {symbol}")
            except Exception as e:
                self._log(f"合约错误: {e}")
                return

        for i, w in enumerate(self.wallets):
            try:
                w.status = "Querying"
                self.after(0, self._update_table_row, i)

                native_bal = self.w3.eth.get_balance(w.address)
                native_str = f"{Web3.from_wei(native_bal, 'ether'):.6f}"

                if t == "Native":
                    w.balance = f"{native_str} {symbol}"
                elif t == "ERC20":
                    tok_bal = contract.functions.balanceOf(w.address).call()
                    tok_str = f"{Decimal(tok_bal) / Decimal(10 ** decimals):.6f}"
                    w.balance = f"{tok_str} {symbol}"
                    w.token_balance = str(tok_bal)
                else:
                    nft_bal = contract.functions.balanceOf(w.address).call()
                    native_sym = NETWORKS.get(self.network_var.get(), {}).get("symbol", "ETH")
                    w.balance = f"{nft_bal} NFTs ({native_str} {native_sym})"

                w.status = "Ready"
            except Exception as e:
                w.balance = "错误"
                w.status = "Failed"
                self._log(f"[{w.address[:8]}...] 查询错误: {e}")

            self.after(0, self._update_table_row, i)

        self._log("余额查询完成。")

    # ── 开始转账 ──────────────────────────────────────────────────────────────
    def _start_transfer(self):
        if not self.w3 or not self.w3.is_connected():
            messagebox.showwarning("未连接", "请先连接 RPC 网络。")
            return
        if not self.wallets:
            messagebox.showinfo("无钱包", "请先导入钱包文件。")
            return
        if self.running:
            return

        confirm = messagebox.askyesno("确认转账",
                                      f"确定要使用 {len(self.wallets)} 个钱包开始批量转账吗？")
        if not confirm:
            return

        self.running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self._transfer_thread, daemon=True).start()

    def _stop_transfer(self):
        self.running = False
        self._log("正在停止，等待当前交易完成...")
        self.stop_btn.configure(state="disabled")

    def _is_eip1559(self) -> bool:
        """检测当前链是否支持 EIP-1559。"""
        try:
            latest = self.w3.eth.get_block("latest")
            return "baseFeePerGas" in latest
        except Exception:
            return False

    def _get_gas_params(self, auto_gas: bool, manual_gas_gwei: float | None) -> dict:
        """根据链类型返回合适的 gas 价格参数，自动模式会加 20% buffer。"""
        if not auto_gas and manual_gas_gwei is not None:
            return {"gasPrice": Web3.to_wei(manual_gas_gwei, "gwei")}

        if self._is_eip1559():
            latest = self.w3.eth.get_block("latest")
            base_fee = latest["baseFeePerGas"]
            try:
                priority_fee = self.w3.eth.max_priority_fee_per_gas
            except Exception:
                priority_fee = Web3.to_wei(1.5, "gwei")
            max_fee = int(base_fee * 2) + priority_fee
            return {
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": priority_fee,
            }
        else:
            gas_price = self.w3.eth.gas_price
            buffered = int(gas_price * 1.2)
            return {"gasPrice": buffered}

    def _estimate_gas_with_buffer(self, tx: dict) -> int:
        """估算 gas 并加 20% buffer 防止 out-of-gas。"""
        estimated = self.w3.eth.estimate_gas(tx)
        return int(estimated * 1.2)

    def _transfer_thread(self):
        t = self.transfer_type.get()
        net = NETWORKS.get(self.network_var.get(), {})
        chain_id = int(self.chain_id_entry.get() or net.get("chain_id", 1))
        explorer = net.get("explorer", "")

        try:
            delay = float(self.delay_entry.get() or "1")
        except ValueError:
            delay = 1.0

        auto_gas = self.gas_auto.get()
        manual_gas_gwei = None
        if not auto_gas:
            try:
                manual_gas_gwei = float(self.gas_entry.get())
            except ValueError:
                self._log("Gas 价格无效，使用自动")
                auto_gas = True

        manual_gas_limit = None
        gl = self.gaslimit_entry.get().strip()
        if gl:
            try:
                manual_gas_limit = int(gl)
            except ValueError:
                pass

        eip1559 = self._is_eip1559()
        self._log(f"Gas 模式: {'EIP-1559' if eip1559 else 'Legacy'}")

        try:
            amount_str = self.amount_entry.get().strip() or "0"
            amount = Decimal(amount_str)
        except Exception:
            amount = Decimal("0")

        try:
            reserve_str = self.reserve_entry.get().strip() or "0"
            reserve = Decimal(reserve_str)
        except Exception:
            reserve = Decimal("0")

        contract = None
        decimals = 18
        symbol = net.get("symbol", "ETH")

        if t == "ERC20":
            addr = self.contract_entry.get().strip()
            try:
                contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(addr), abi=ERC20_ABI)
                decimals = contract.functions.decimals().call()
                symbol = contract.functions.symbol().call()
            except Exception as e:
                self._log(f"合约错误: {e}")
                self._finish_transfer()
                return
        elif t == "ERC721":
            addr = self.contract_entry.get().strip()
            try:
                contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(addr), abi=ERC721_ABI)
            except Exception as e:
                self._log(f"合约错误: {e}")
                self._finish_transfer()
                return

        total = len(self.wallets)
        success_count = 0
        fail_count = 0

        for i, w in enumerate(self.wallets):
            if not self.running:
                w.status = "Skipped"
                self.after(0, self._update_table_row, i)
                continue

            w.status = "Pending"
            self.after(0, self._update_table_row, i)
            self.after(0, self.progress.set, (i + 1) / total)

            try:
                nonce = self.w3.eth.get_transaction_count(w.address)
                gas_params = self._get_gas_params(auto_gas, manual_gas_gwei)

                if t == "Native":
                    tx_hash = self._send_native(w, chain_id, nonce, gas_params,
                                                manual_gas_limit, amount, reserve)
                elif t == "ERC20":
                    tx_hash = self._send_erc20(w, contract, chain_id, nonce, gas_params,
                                               manual_gas_limit, amount, reserve, decimals)
                else:
                    token_ids_str = self.token_id_entry.get().strip()
                    token_ids = [int(x.strip()) for x in token_ids_str.split(",") if x.strip()]
                    tx_hash = self._send_erc721(w, contract, chain_id, nonce, gas_params,
                                                manual_gas_limit, token_ids)

                if tx_hash:
                    w.tx_hash = tx_hash
                    w.status = "Success"
                    success_count += 1
                    link = f"{explorer}{tx_hash}" if explorer else tx_hash
                    self._log(f"[{i+1}/{total}] {w.address[:8]}... -> {w.to_address[:8]}... TX: {link}")
                else:
                    w.status = "Skipped"
                    self._log(f"[{i+1}/{total}] {w.address[:8]}... 已跳过 (余额不足或数量为零)")

            except Exception as e:
                w.status = "Failed"
                fail_count += 1
                self._log(f"[{i+1}/{total}] {w.address[:8]}... 失败: {e}")

            self.after(0, self._update_table_row, i)

            if i < total - 1 and self.running:
                time.sleep(delay)

        self._log(f"转账完成。成功: {success_count}, 失败: {fail_count}, "
                  f"跳过: {total - success_count - fail_count}")
        self._finish_transfer()

    def _send_native(self, w, chain_id, nonce, gas_params, gas_limit, amount, reserve):
        balance = self.w3.eth.get_balance(w.address)

        # 先估算 gas limit
        est_tx = {
            "from": w.address,
            "to": w.to_address,
            "value": balance // 2,  # 用一半余额估算，避免余额不足导致估算失败
            **gas_params,
            "nonce": nonce,
            "chainId": chain_id,
        }
        if gas_limit:
            est_gas = gas_limit
        else:
            try:
                est_gas = self._estimate_gas_with_buffer(est_tx)
            except Exception:
                est_gas = 21000

        # 计算 gas 成本（用于全部转出时扣除）
        if "maxFeePerGas" in gas_params:
            gas_cost = gas_params["maxFeePerGas"] * est_gas
        else:
            gas_cost = gas_params["gasPrice"] * est_gas

        if amount == 0:
            reserve_wei = Web3.to_wei(reserve, "ether")
            send_value = balance - gas_cost - reserve_wei
        else:
            send_value = Web3.to_wei(amount, "ether")

        if send_value <= 0:
            return None

        tx = {
            "from": w.address,
            "to": w.to_address,
            "value": send_value,
            "gas": est_gas,
            **gas_params,
            "nonce": nonce,
            "chainId": chain_id,
        }

        signed = self.w3.eth.account.sign_transaction(tx, w.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def _send_erc20(self, w, contract, chain_id, nonce, gas_params, gas_limit, amount, reserve, decimals):
        balance = contract.functions.balanceOf(w.address).call()
        unit = Decimal(10 ** decimals)

        if amount == 0:
            reserve_raw = int(reserve * unit)
            send_amount = balance - reserve_raw
        else:
            send_amount = int(amount * unit)

        if send_amount <= 0:
            return None

        tx = contract.functions.transfer(w.to_address, send_amount).build_transaction({
            "from": w.address,
            **gas_params,
            "nonce": nonce,
            "chainId": chain_id,
        })

        if gas_limit:
            tx["gas"] = gas_limit
        else:
            tx["gas"] = self._estimate_gas_with_buffer(tx)

        signed = self.w3.eth.account.sign_transaction(tx, w.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def _send_erc721(self, w, contract, chain_id, nonce, gas_params, gas_limit, token_ids):
        if not token_ids:
            return None

        last_hash = None
        for tid in token_ids:
            if not self.running:
                break
            try:
                owner = contract.functions.ownerOf(tid).call()
                if owner.lower() != w.address.lower():
                    self._log(f"  Token #{tid}: 不属于 {w.address[:8]}...，已跳过")
                    continue
            except Exception:
                self._log(f"  Token #{tid}: 所有权查询失败，已跳过")
                continue

            tx = contract.functions.transferFrom(w.address, w.to_address, tid).build_transaction({
                "from": w.address,
                **gas_params,
                "nonce": nonce,
                "chainId": chain_id,
            })
            if gas_limit:
                tx["gas"] = gas_limit
            else:
                tx["gas"] = self._estimate_gas_with_buffer(tx)

            signed = self.w3.eth.account.sign_transaction(tx, w.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            last_hash = tx_hash.hex()
            nonce += 1
            self._log(f"  Token #{tid} 已转移。TX: {last_hash}")

        return last_hash

    def _finish_transfer(self):
        self.running = False
        self.after(0, lambda: self.start_btn.configure(state="normal"))
        self.after(0, lambda: self.stop_btn.configure(state="disabled"))


# ── 启动 ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
