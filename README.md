# tvgw: обход блокировки YouTube для Яндекс ТВ

Шлюз на отдельной Linux-машине (LXC в Proxmox), который пропускает через [zapret2](https://github.com/bol-van/zapret2) трафик **только одного устройства** — телевизора. Остальная домашняя сеть работает как раньше, роутер не настраивается.

Схема не привязана к Яндекс ТВ: она работает для любого устройства в сети (Android TV, Apple TV, приставка, консоль) — нужны только его IP и MAC. Яндекс ТВ — самый сложный случай, поэтому здесь он основной. На обычном Android TV проще: в настройках Wi-Fi укажите статический шлюз (адрес tvgw), и тогда `tv-arp` не нужен — хватит nftables и zapret2.

## Зачем

На Яндекс ТВ (YaOS X, Android 12) YouTube из-за замедления не открывается или тормозит. Поставить zapret на сам ТВ нельзя (нет root), VPN-приложение не хочется. Поэтому трафик ТВ заворачивается на отдельную машину, где zapret2 обрабатывает пакеты YouTube.

## Как это работает

```
ТВ (DHCP, Wi-Fi) ──► tvgw ──► роутер ──► интернет
                      │
                      ├─ ARP-подмена: ТВ думает, что шлюз 192.168.31.1 — это tvgw
                      ├─ ip_forward + masquerade (только для ТВ)
                      ├─ reject UDP 443 (YouTube переходит с QUIC на TCP)
                      └─ nfqws2 (zapret2): только YouTube/googlevideo, TCP 443
```

Почему ARP, а не «прописать шлюз на ТВ»: Яндекс ТВ игнорирует статический IP/шлюз и всегда работает по DHCP со шлюзом роутера. Поэтому `tv-arp.py` раз в 2 секунды отправляет ТВ ARP-ответ «192.168.31.1 находится по MAC tvgw». Подмена односторонняя: ARP-кеш меняется только у ТВ, роутер и другие устройства ничего не знают. Masquerade на tvgw делает так, что ответы роутера возвращаются на tvgw, а не мимо него.

Безопасность отказа:
- если tvgw выключен, ARP-запись на ТВ протухает (минуты) и он возвращается на роутер сам;
- при остановке `tv-arp` скрипт 3 раза шлёт ТВ настоящий MAC роутера.

## Что в репозитории

| Файл | Куда на tvgw |
|---|---|
| `tv-arp.py` | `/usr/local/bin/tv-arp.py` |
| `systemd/tv-arp.service` | `/etc/systemd/system/tv-arp.service` |
| `systemd/zapret2.service` | `/etc/systemd/system/zapret2.service` |
| `nftables.conf` | `/etc/nftables.conf` |
| `99-tvgw.conf` | `/etc/sysctl.d/99-tvgw.conf` |
| `zapret2.config` | `/opt/zapret2/config` |

`zapret2.config` — урезанный конфиг: профили только `TCP_YT_list.txt` (YouTube) и `googlevideo.com`, порт TCP 443, UDP пусто, режим `hostlist`. Стратегии подбирает `circular_locked` из [zator](https://github.com/IndeecFOX/zator) (lua-скрипты в `/opt/zator`).

## Установка

Нужна машина с Debian 12/13 в той же подсети, что и ТВ. В LXC (unprivileged) нужны `nesting=1` и модули `nfnetlink_queue`, `nft_queue`, загруженные на хосте Proxmox.

1. Поставить пакеты:
   ```bash
   sudo apt install nftables python3 conntrack tcpdump
   ```
2. Установить zapret2 в `/opt/zapret2` и zator в `/opt/zator` (в моём случае скопировано с рабочей машины, где они уже стоят; с нуля — по инструкциям проектов). Положить `zapret2.config` в `/opt/zapret2/config`.
3. Записать в `tv-arp.py` свои значения (константы в начале файла):
   - `TV_IP`, `TV_MAC` — IP и MAC телевизора (Настройки → Сеть → Wi-Fi → О сети);
   - `GW_IP`, `GW_MAC` — IP и MAC роутера (`ip neigh show 192.168.31.1`);
   - `IFACE` — сетевой интерфейс tvgw.
   
   В `nftables.conf` заменить `192.168.31.217` на IP телевизора.
4. Разложить файлы по таблице выше и включить:
   ```bash
   sudo sysctl --system
   sudo systemctl daemon-reload
   sudo systemctl enable --now nftables zapret2 tv-arp
   ```
   `net.ipv4.conf.all.send_redirects=0` обязателен, иначе tvgw будет слать ТВ ICMP-redirect, указывая на роутер.

## Настройка на ТВ

Ничего менять не нужно: IP по DHCP, Wi-Fi как обычно. Единственное, что стоит сделать — **закрепить за ТВ постоянный IP в DHCP-резервации роутера** (иначе после смены IP правила nft и `TV_IP` в скрипте перестанут подходить). После запуска `tv-arp` переподключите Wi-Fi на ТВ или подождите пару минут и откройте YouTube.

## Проверка

```bash
# трафик ТВ идёт через tvgw
sudo conntrack -L | grep 192.168.31.217
sudo tcpdump -ni eth0 host 192.168.31.217

# сервисы
systemctl is-active nftables zapret2 tv-arp
sudo nft list ruleset
sysctl net.ipv4.ip_forward
```

## Откат

```bash
sudo systemctl disable --now tv-arp     # ТВ вернётся на роутер (скрипт сам вернёт настоящий MAC)
# при желании полностью:
sudo systemctl disable --now zapret2 nftables
```
Если tvgw — отдельный контейнер, его можно просто остановить: `pct stop <id>`.

## Ограничения

- Через tvgw идёт **весь** трафик ТВ, а не только YouTube (zapret2 обрабатывает лишь hostlist YouTube). tvgw — единственная точка отказа для ТВ, пока работает `tv-arp`.
- Только IPv4. Если роутер раздаёт ТВ IPv6, этот трафик пойдёт мимо шлюза.
- Не сработает, если на роутере включена изоляция клиентов Wi-Fi или защита от ARP-спуфинга.
- Нужен ТВ с постоянным IP/MAC (учтите приватный/случайный MAC в настройках Wi-Fi на ТВ).
