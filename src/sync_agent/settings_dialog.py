"""설정 다이얼로그 (tkinter)."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.sync_agent.config import AppConfig


class SettingsDialog:
    """설정 다이얼로그.

    Supabase 연결 정보와 감시 경로를 설정합니다.
    """

    def __init__(self, config: AppConfig, on_save: callable = None) -> None:
        """초기화.

        Args:
            config: 현재 설정
            on_save: 저장 시 콜백
        """
        self.config = config
        self.on_save = on_save
        self.result = False

    def show(self) -> bool:
        """다이얼로그 표시.

        Returns:
            저장 여부
        """
        self.root = tk.Tk()
        self.root.title("GFX Sync 설정")
        self.root.geometry("500x400")
        self.root.resizable(False, False)

        # 아이콘 설정 (Windows)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        # 중앙 정렬
        self.root.eval("tk::PlaceWindow . center")

        self._create_widgets()
        self._load_values()

        self.root.mainloop()
        return self.result

    def _create_widgets(self) -> None:
        """위젯 생성."""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === Supabase 섹션 ===
        supabase_frame = ttk.LabelFrame(main_frame, text="Supabase 연결", padding="10")
        supabase_frame.pack(fill=tk.X, pady=(0, 10))

        # URL
        ttk.Label(supabase_frame, text="Project URL:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(supabase_frame, textvariable=self.url_var, width=50)
        self.url_entry.grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(5, 0))

        # Service Key
        ttk.Label(supabase_frame, text="Service Key:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        self.key_var = tk.StringVar()
        self.key_entry = ttk.Entry(
            supabase_frame, textvariable=self.key_var, width=50, show="*"
        )
        self.key_entry.grid(row=1, column=1, sticky=tk.EW, pady=2, padx=(5, 0))

        # Key 보기 체크박스
        self.show_key_var = tk.BooleanVar(value=False)
        self.show_key_cb = ttk.Checkbutton(
            supabase_frame,
            text="Key 보기",
            variable=self.show_key_var,
            command=self._toggle_key_visibility,
        )
        self.show_key_cb.grid(row=2, column=1, sticky=tk.W, pady=2, padx=(5, 0))

        supabase_frame.columnconfigure(1, weight=1)

        # === 경로 섹션 ===
        path_frame = ttk.LabelFrame(main_frame, text="경로 설정", padding="10")
        path_frame.pack(fill=tk.X, pady=(0, 10))

        # 감시 경로
        ttk.Label(path_frame, text="감시 폴더:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.watch_path_var = tk.StringVar()
        self.watch_path_entry = ttk.Entry(
            path_frame, textvariable=self.watch_path_var, width=40
        )
        self.watch_path_entry.grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(5, 0))
        ttk.Button(path_frame, text="찾아보기", command=self._browse_watch_path).grid(
            row=0, column=2, pady=2, padx=(5, 0)
        )

        # 큐 DB 경로
        ttk.Label(path_frame, text="큐 DB 경로:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        self.queue_path_var = tk.StringVar()
        self.queue_path_entry = ttk.Entry(
            path_frame, textvariable=self.queue_path_var, width=40
        )
        self.queue_path_entry.grid(row=1, column=1, sticky=tk.EW, pady=2, padx=(5, 0))
        ttk.Button(path_frame, text="찾아보기", command=self._browse_queue_path).grid(
            row=1, column=2, pady=2, padx=(5, 0)
        )

        path_frame.columnconfigure(1, weight=1)

        # === 고급 설정 섹션 ===
        advanced_frame = ttk.LabelFrame(main_frame, text="고급 설정", padding="10")
        advanced_frame.pack(fill=tk.X, pady=(0, 10))

        # 배치 크기
        ttk.Label(advanced_frame, text="배치 크기:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.batch_size_var = tk.StringVar()
        self.batch_size_entry = ttk.Entry(
            advanced_frame, textvariable=self.batch_size_var, width=10
        )
        self.batch_size_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=(5, 0))

        # 플러시 간격
        ttk.Label(advanced_frame, text="플러시 간격 (초):").grid(
            row=0, column=2, sticky=tk.W, pady=2, padx=(20, 0)
        )
        self.flush_interval_var = tk.StringVar()
        self.flush_interval_entry = ttk.Entry(
            advanced_frame, textvariable=self.flush_interval_var, width=10
        )
        self.flush_interval_entry.grid(
            row=0, column=3, sticky=tk.W, pady=2, padx=(5, 0)
        )

        # === 버튼 ===
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            button_frame, text="테스트 연결", command=self._test_connection
        ).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="취소", command=self._on_cancel).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(button_frame, text="저장", command=self._on_save).pack(side=tk.RIGHT)

    def _load_values(self) -> None:
        """현재 설정값 로드."""
        self.url_var.set(self.config.supabase_url or "")
        self.key_var.set(self.config.supabase_service_key or "")
        self.watch_path_var.set(self.config.gfx_watch_path or "C:/GFX/output")
        self.queue_path_var.set(
            self.config.queue_db_path or "C:/GFX/sync_queue/pending.db"
        )
        self.batch_size_var.set(str(self.config.batch_size or 500))
        self.flush_interval_var.set(str(self.config.flush_interval or 5.0))

    def _toggle_key_visibility(self) -> None:
        """Key 표시/숨김 토글."""
        if self.show_key_var.get():
            self.key_entry.config(show="")
        else:
            self.key_entry.config(show="*")

    def _browse_watch_path(self) -> None:
        """감시 폴더 선택."""
        path = filedialog.askdirectory(
            title="감시 폴더 선택",
            initialdir=self.watch_path_var.get() or "C:/",
        )
        if path:
            self.watch_path_var.set(path)

    def _browse_queue_path(self) -> None:
        """큐 DB 경로 선택."""
        path = filedialog.asksaveasfilename(
            title="큐 DB 경로 선택",
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")],
            initialdir=self.queue_path_var.get() or "C:/",
        )
        if path:
            self.queue_path_var.set(path)

    def _test_connection(self) -> None:
        """Supabase 연결 테스트."""
        url = self.url_var.get().strip()
        key = self.key_var.get().strip()

        if not url or not key:
            messagebox.showerror("오류", "URL과 Service Key를 입력하세요.")
            return

        try:
            from supabase import create_client

            client = create_client(url, key)
            # 간단한 쿼리로 연결 테스트
            client.table("gfx_sessions").select("id").limit(1).execute()
            messagebox.showinfo("성공", "Supabase 연결 성공!")
        except Exception as e:
            messagebox.showerror("연결 실패", f"연결 실패: {e}")

    def _validate(self) -> bool:
        """입력값 검증."""
        if not self.url_var.get().strip():
            messagebox.showerror("오류", "Supabase URL을 입력하세요.")
            return False

        if not self.key_var.get().strip():
            messagebox.showerror("오류", "Service Key를 입력하세요.")
            return False

        if not self.watch_path_var.get().strip():
            messagebox.showerror("오류", "감시 폴더를 입력하세요.")
            return False

        try:
            int(self.batch_size_var.get())
        except ValueError:
            messagebox.showerror("오류", "배치 크기는 숫자여야 합니다.")
            return False

        try:
            float(self.flush_interval_var.get())
        except ValueError:
            messagebox.showerror("오류", "플러시 간격은 숫자여야 합니다.")
            return False

        return True

    def _on_save(self) -> None:
        """저장 버튼 클릭."""
        if not self._validate():
            return

        # 설정 업데이트
        self.config.supabase_url = self.url_var.get().strip()
        self.config.supabase_service_key = self.key_var.get().strip()
        self.config.gfx_watch_path = self.watch_path_var.get().strip()
        self.config.queue_db_path = self.queue_path_var.get().strip()
        self.config.batch_size = int(self.batch_size_var.get())
        self.config.flush_interval = float(self.flush_interval_var.get())

        # 파일에 저장
        self.config.save()

        if self.on_save:
            self.on_save()

        self.result = True
        self.root.destroy()

    def _on_cancel(self) -> None:
        """취소 버튼 클릭."""
        self.result = False
        self.root.destroy()


def show_settings_dialog(config: AppConfig, on_save: callable = None) -> bool:
    """설정 다이얼로그 표시.

    Args:
        config: 현재 설정
        on_save: 저장 시 콜백

    Returns:
        저장 여부
    """
    dialog = SettingsDialog(config, on_save)
    return dialog.show()
