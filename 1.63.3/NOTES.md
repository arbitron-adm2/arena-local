# 1.63.3 — клиент и ассеты

Скачано с CDN: клиент `engine/1.63.3/Wormix.swf` (2 903 769 Б, Last-Modified 02.11.2026),
данные `engine/1.63.3/data/...`, звук и аватары `engine/storage/...`.

## Состав

```
Wormix.swf        2,8 МБ  клиент 1.63.3
data/              20 МБ  common/, lang/, resconfigs/, social/
storage/          8,3 МБ  sound/ (sounds_1.53.swf, music_theme_1, units/), social/vkontakte/avatar
```

## Чего нет

- **preloader** — под 1.63.3 имена `preloader_251…263.swf` и `preloader.swf` отдают 404;
  вероятно, лончер сменил имя или отдаёт загрузчик с другого хоста. Пока клиент
  грузится напрямую с параметрами из `/session`.
- **data/serializers.xml** — в 1.63.3 по этому пути 404; список сериализаторов,
  похоже, уехал в другой файл/внутрь клиента.

## Запуск

```bash
python3 server.py
# затем открыть
http://127.0.0.1:18371/?v=1.63.3
```

Без `?v=` страница отдаёт старый стенд 1.61.7 из `assets/` + `patched/`.

## Баннер secureSWF

`Wormix.swf` содержит `DefineEditText` (tag 37 на 6304906) с текстом
`<a href='kindi.com'>Protected by secureSWF<br/>Demo version.</a>`.
В `patched/Wormix.swf` этот текст заменён пробелами (длина сохранена, остальной файл 1:1).

Запуск: `?v=1.63.3&patched=1`. Баннера нет, но клиент по-прежнему не стартует:
в логе Ruffle «Loaded SWF version 13, resolution 800x600 @ 30 FPS» и дальше тишина,
запросов к `/session` и `/api` нет — стоп в байткоде, а не в текстовом теге.
