# Banco PostgreSQL local

O PostgreSQL operacional do LiberRotas persiste seus arquivos em
`database/postgres`, dentro deste workspace. O Docker Compose monta essa pasta
em `/var/lib/postgresql/data` no contêiner.

Não edite, copie parcialmente nem abra os arquivos de `database/postgres`
enquanto o contêiner PostgreSQL estiver em execução. Para transportar ou
restaurar o banco, use sempre um backup lógico criado com `pg_dump`.

Os backups lógicos locais ficam em `backups/postgresql` e são ignorados pelo
Git porque podem conter dados pessoais e comerciais.

Para criar um backup lógico enquanto o sistema estiver ligado, execute na raiz
do workspace:

```powershell
.\BACKUP_BANCO.ps1
```

O comando mostra o caminho, o tamanho e o SHA-256 do arquivo gerado.

Para parar normalmente o ambiente sem apagar dados, execute na raiz do
workspace:

```powershell
.\PARAR_LIBERROTAS.ps1
```

Nunca use `docker compose down -v` como procedimento normal de parada.
