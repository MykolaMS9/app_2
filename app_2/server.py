import asyncio
import datetime
import logging

import aiohttp
import aiofile
import websockets
import names
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK

logging.basicConfig(level=logging.INFO)


async def request(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    r = await response.json()
                    return r
                logging.error(f'Error status: {response.status} for {url}')
        except aiohttp.ClientConnectionError as e:
            logging.error(f"Connection error {url}: {e}")
        return None


def transformer(list_):
    format_date = '^15'
    format_c = '^14'
    header_1 = f"{'':{format_date}}||"
    header_2 = f"{'date':{format_date}}||"
    LAST_EL = list_[-1]
    for val_ in LAST_EL:
        for currency in LAST_EL[val_].keys():
            header_1 += f"{currency:^29}||"
            header_2 += f"{'sale':{format_c}}|{'purchase':{format_c}}||"
    result = [header_1, header_2]

    for element in list_:
        if not element:
            result.append('No data for this date')
        else:
            for dict_ in element:
                res = f'{dict_:{format_date}}||'
                for key, value in element[dict_].items():
                    res += f"{value['sale']:{format_c}}|{value['purchase']:{format_c}}||"
                result.append(res)

    return result


async def get_exchange(url, cur):
    res = await request(url)
    try:
        currency_list = res['exchangeRate']
        result = {}
        for currency in currency_list:
            if currency['currency'] in cur:
                sale = currency.get('saleRate')
                if not sale:
                    sale = currency.get('saleRateNB')
                purchase = currency.get('purchaseRate')
                if not purchase:
                    purchase = currency.get('purchaseRateNB')
                result[currency['currency']] = {'sale': sale, 'purchase': purchase}
        dic = {res['date']: result}
        return dic
    except:
        return None


async def get_response(urls, cur):
    for url in urls:
        yield get_exchange(url, cur)


class Server:
    clients = set()
    file_name = 'exchange_log.log'

    async def register(self, ws: WebSocketServerProtocol):
        ws.name = names.get_full_name()
        self.clients.add(ws)
        logging.info(f'{ws.remote_address} connects')

    async def unregister(self, ws: WebSocketServerProtocol):
        self.clients.remove(ws)
        logging.info(f'{ws.remote_address} disconnects')

    async def send_to_clients(self, message: str):
        if self.clients:
            [await client.send(message) for client in self.clients]

    async def ws_handler(self, ws: WebSocketServerProtocol):
        await self.register(ws)
        try:
            await self.distribute(ws)
        except ConnectionClosedOK:
            pass
        finally:
            await self.unregister(ws)

    async def file_logger(self, message):
        async with aiofile.async_open(self.file_name, 'a') as f:
            await f.write(f'{datetime.datetime.now()}: {message}\n')

    async def distribute(self, ws: WebSocketServerProtocol):
        async for message in ws:
            if message.startswith('exchange'):
                inp_list = message.split()
                if len(inp_list) == 1:
                    n = 1
                    currency_list = ['EUR', 'USD']
                else:
                    try:
                        n = inp_list[1]
                        if int(n) > 10:
                            n = 10
                        currency_list = [s.upper() for s in inp_list[2:]]
                    except:
                        n = 1
                        currency_list = [s.upper() for s in inp_list[1:]]
                if not currency_list:
                    currency_list = ['EUR', 'USD']

                url = 'https://api.privatbank.ua/p24api/exchange_rates?json&date='
                urls = []
                now = datetime.datetime.now()
                for day_ in range(int(n)):
                    date = (now.date() - datetime.timedelta(days=day_)).strftime("%d.%m.%Y")
                    urls.append(url + date)

                result = []
                async for url in get_response(urls, currency_list):
                    result.append(url)
                r = await asyncio.gather(*result)
                try:
                    message_print = transformer(r)
                    message_ = f'exchange: {", ".join(currency_list)}  for {n} {"day" if int(n)==1 else "days"}'
                except Exception as err:
                    message_print = ['Something wrong!']
                    message_ = f'exchange: {", ".join(currency_list)}  for {n} {"day" if int(n)==1 else "days"} wrong as {err}'
                for m_print in message_print:
                    await self.send_to_clients(m_print)
                await self.file_logger(message_)
            else:
                await self.send_to_clients(f"{ws.name}: {message}")


async def main():
    server = Server()
    async with websockets.serve(server.ws_handler, 'localhost', 8080):
        await asyncio.Future()  # run forever


if __name__ == '__main__':
    asyncio.run(main())
