"""Publicação recuperável dos arquivos do lote, sob um único bloqueio local."""
import fcntl
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

FORMATO = "guicredito-pessoas/1"
RAIZ = {"manifesto.json", "pessoas.xlsx", "relatorio.html", "revisao.html"}
POR_CASO = {"pessoas.json", "consultas.json", "contatos.json", "evidencias.json"}


def escrever_json(arquivo, dados):
    arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def ler_json(arquivo):
    if arquivo.is_symlink() or not arquivo.is_file():
        raise ValueError("Arquivo do lote ausente ou inseguro.")
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _marca(arquivo):
    if arquivo.is_symlink():
        raise ValueError("A planilha não pode ser um link.")
    if not arquivo.exists():
        return None
    with arquivo.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _relativo_valido(nome):
    if nome in RAIZ:
        return True
    itens = nome.split("/")
    return len(itens) == 2 and re.fullmatch("[0-9]{20}", itens[0]) and (
        itens[1] in POR_CASO or re.fullmatch(r"evidencia-[a-f0-9]{64}\.txt", itens[1])
    )


class Lote:
    def __init__(self, pasta, criar=False):
        self.pasta = Path(pasta)
        self.criar = criar
        self.lock = self.pasta / ".pessoas.lock"
        self.preparo = self.pasta / ".pessoas-preparo"
        self.pendente = self.pasta / ".pessoas-publicar"
        self._fd = None

    def __enter__(self):
        if self.pasta.is_symlink():
            raise ValueError("A pasta do lote não pode ser um link.")
        if self.criar:
            self.pasta.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.pasta.is_dir():
            raise ValueError("Lote inexistente.")
        if not self.lock.exists() and (not self.criar or any(self.pasta.iterdir())):
            raise ValueError("Escolha uma pasta vazia ou um lote de pessoas existente.")
        self._fd = os.open(self.lock, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if self.criar else 0), 0o600)
        try:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("O lote está em uso.") from None
            dono = os.read(self._fd, 100)
            if not dono and self.criar and set(self.pasta.iterdir()) == {self.lock}:
                os.write(self._fd, FORMATO.encode())
            elif dono != FORMATO.encode():
                raise ValueError("Pasta incompatível com o formato do lote.")
            if any(p.is_symlink() for p in (self.preparo, self.pendente)):
                raise ValueError("Área de trabalho do lote insegura.")
            if self.preparo.exists():
                shutil.rmtree(self.preparo)
            if self.pendente.exists():
                self._aplicar()
            self.marca_excel = _marca(self.pasta / "pessoas.xlsx")
            if not self.criar and not (self.pasta / "manifesto.json").is_file():
                raise ValueError("Lote ainda não inicializado.")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def caminho(self, nome):
        if not _relativo_valido(nome):
            raise ValueError("Caminho fora das saídas da etapa pessoas.")
        p = self.pasta / nome
        if p.is_symlink() or p.parent.is_symlink():
            raise ValueError("Saída do lote contém link simbólico.")
        return p

    def manifesto(self):
        caminho = self.caminho("manifesto.json")
        if not caminho.exists():
            return None
        estado = ler_json(caminho)
        if estado.get("formato") != FORMATO:
            raise ValueError("Formato do lote incompatível.")
        return estado

    def _excel_livre(self):
        if any((self.pasta / nome).exists() for nome in ("~$pessoas.xlsx", ".~lock.pessoas.xlsx#")):
            raise ValueError("Feche a planilha antes de atualizar o lote.")

    def publicar(self, montar):
        """Montar uma geração completa. A partir do rename, a intenção é recuperável."""
        self._excel_livre()
        if _marca(self.pasta / "pessoas.xlsx") != self.marca_excel:
            raise ValueError("A planilha mudou durante a operação. Reabra o lote.")
        antigo = self.manifesto() or {}
        self.preparo.mkdir(mode=0o700)
        try:
            montar(self.preparo)
            arquivos = set()
            for p in self.preparo.rglob("*"):
                if p.is_symlink():
                    raise ValueError("Saída temporária insegura.")
                if p.is_file():
                    nome = p.relative_to(self.preparo).as_posix()
                    self.caminho(nome)
                    p.chmod(0o600)
                    arquivos.add(nome)
            if "manifesto.json" not in arquivos or "pessoas.xlsx" not in arquivos:
                raise ValueError("Geração incompleta.")
            anteriores = set(antigo.get("arquivos", []))
            for nome in arquivos - anteriores:
                if self.caminho(nome).exists():
                    raise ValueError("Arquivo preexistente não pertence à geração do lote.")
            manifest = ler_json(self.preparo / "manifesto.json")
            manifest["arquivos"] = sorted(arquivos)
            escrever_json(self.preparo / "manifesto.json", manifest)
            remover = sorted(anteriores - arquivos)
            for nome in remover:
                self.caminho(nome)
            escrever_json(self.preparo / ".operacao.json", {
                "arquivos": sorted(arquivos), "remover": remover, "excel_anterior": self.marca_excel,
                "excel_novo": _marca(self.preparo / "pessoas.xlsx")
            })
            if _marca(self.pasta / "pessoas.xlsx") != self.marca_excel:
                raise ValueError("A planilha mudou durante a operação. Reabra o lote.")
            self.preparo.rename(self.pendente)
        finally:
            if self.preparo.exists():
                shutil.rmtree(self.preparo)
        self._aplicar()
        self.marca_excel = _marca(self.pasta / "pessoas.xlsx")

    def _aplicar(self):
        self._excel_livre()
        op = ler_json(self.pendente / ".operacao.json")
        if _marca(self.caminho("pessoas.xlsx")) not in {op["excel_anterior"], op["excel_novo"]}:
            raise ValueError("A planilha mudou durante uma atualização interrompida. Preserve a edição antes de recuperar.")
        # O manifesto é o último arquivo publicado. As operações são idempotentes.
        for nome in op["remover"]:
            destino = self.caminho(nome)
            destino.unlink(missing_ok=True)
            if destino.parent != self.pasta and destino.parent.is_dir() and not any(destino.parent.iterdir()):
                destino.parent.rmdir()
        for nome in sorted(op["arquivos"], key=lambda n: (n == "manifesto.json", n)):
            destino = self.caminho(nome)
            origem = self.pendente / nome
            if origem.is_symlink() or origem.parent.is_symlink():
                raise ValueError("Arquivo pendente inseguro.")
            if origem.exists():
                destino.parent.mkdir(mode=0o700, exist_ok=True)
                origem.replace(destino)
            elif not destino.is_file():
                raise ValueError("Arquivo ausente na recuperação do lote.")
        # Retirar a área da fila antes de desmontá-la evita depender de um journal já removido.
        self.pendente.rename(self.preparo)
        shutil.rmtree(self.preparo)
