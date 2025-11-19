import os
import pickle
import threading
import time
from binance.client import Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# Binance API credentials
API_KEY = ''
API_SECRET = ''

# Telegram Bot Token
BOT_TOKEN = ''

# Data file for persistence
DATA_FILE = 'demo_account.pkl'

# Initial demo balance
INITIAL_BALANCE = 100000.0

# Binance Client
client = Client(API_KEY, API_SECRET)

# Load or initialize data
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'rb') as f:
            return pickle.load(f)
    else:
        return {
            'balance': INITIAL_BALANCE,
            'holdings': {},  # coin: {'amount': float, 'avg_price': float, 'take_profit': float or None, 'stop_loss': float or None}
            'alerts': [],    # list of {'symbol': str, 'price': float, 'direction': 'above' or 'below'}
            'chat_id': None  # To store chat_id for notifications
        }

# Save data
def save_data(data):
    with open(DATA_FILE, 'wb') as f:
        pickle.dump(data, f)

# Global data (for simplicity, assuming single user)
data = load_data()

# Get all USDT pairs
def get_all_usdt_symbols():
    tickers = client.get_all_tickers()
    return [t['symbol'] for t in tickers if t['symbol'].endswith('USDT')]

# Get current price
def get_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except:
        return None

# Calculate portfolio
def get_portfolio():
    balance = data['balance']
    holdings = data['holdings']
    total_value = balance
    pnl = 0.0
    table_rows = []
    for symbol, info in holdings.items():
        current_price = get_price(symbol)
        if current_price:
            value = info['amount'] * current_price
            total_value += value
            profit = (current_price - info['avg_price']) * info['amount']
            pnl += profit
            tp = f"{info['take_profit']:.4f}" if info.get('take_profit') else "-"
            sl = f"{info['stop_loss']:.4f}" if info.get('stop_loss') else "-"
            table_rows.append([
                symbol,
                f"{info['amount']:.4f}",
                f"{info['avg_price']:.4f}",
                f"{current_price:.4f}",
                f"{value:.4f}",
                f"{profit:.4f}",
                tp,
                sl
            ])
    return {
        'balance': balance,
        'total_value': total_value,
        'pnl': pnl,
        'table_rows': table_rows
    }

# Format portfolio as Markdown table
def format_portfolio_table(portfolio):
    if not portfolio['table_rows']:
        return "❌ Tidak ada holdings saat ini."
    
    headers = ["Symbol", "Amount", "Avg Price", "Current Price", "Value", "P&L", "TP", "SL"]
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + "--- | " * len(headers) + "\n"
    for row in portfolio['table_rows']:
        table += "| " + " | ".join(row) + " |\n"
    return table

# Main menu keyboard
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔍 Cek Harga Coin", callback_data='check_price')],
        [InlineKeyboardButton("📊 Lihat Portfolio", callback_data='portfolio')],
        [InlineKeyboardButton("💱 Beli atau Jual Coin", callback_data='trade')],
        [InlineKeyboardButton("🔔 Setel Alert Harga", callback_data='set_alert')],
        [InlineKeyboardButton("⚙️ Setel TP/SL", callback_data='set_tp_sl')],
    ]
    return InlineKeyboardMarkup(keyboard)

# Back button keyboard
def back_button():
    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data='back')],
    ]
    return InlineKeyboardMarkup(keyboard)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    data['chat_id'] = chat_id
    save_data(data)
    await update.message.reply_text("🌟 **Selamat Datang di Bot Trading Demo Binance!** 🌟\n\nPilih menu di bawah ini untuk memulai:", reply_markup=main_menu_keyboard(), parse_mode='Markdown')

# Button handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data

    if data_cb == 'back':
        await query.edit_message_text(text="🌟 **Selamat Datang Kembali!** Pilih menu:", reply_markup=main_menu_keyboard(), parse_mode='Markdown')
    elif data_cb == 'check_price':
        await query.edit_message_text(text="🔍 **Masukkan nama coin** (contoh: BTCUSDT):", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data['state'] = 'check_price'
    elif data_cb == 'portfolio':
        portfolio = get_portfolio()
        text = f"💰 **Balance USDT:** ${portfolio['balance']:.4f}\n📈 **Total Nilai Portfolio:** ${portfolio['total_value']:.4f}\n📉 **Total P&L:** ${portfolio['pnl']:.4f}\n\n**Holdings Anda:**\n{format_portfolio_table(portfolio)}"
        await query.edit_message_text(text=text, reply_markup=back_button(), parse_mode='Markdown')
    elif data_cb == 'trade':
        await query.edit_message_text(text="💱 **Pilih Aksi:** Ketik *'beli'* untuk beli atau *'jual'* untuk jual.", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data['state'] = 'trade_type'
    elif data_cb == 'set_alert':
        await query.edit_message_text(text="🔔 **Setel Alert:** Masukkan symbol, harga, direction (above/below).\nContoh: BTCUSDT 60000 above", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data['state'] = 'set_alert'
    elif data_cb == 'set_tp_sl':
        await query.edit_message_text(text="⚙️ **Setel TP/SL:** Ketik *'tp'* untuk Take-Profit atau *'sl'* untuk Stop-Loss.", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data['state'] = 'set_tp_sl_type'

# Message handler
async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.upper() if 'USDT' in update.message.text.upper() else update.message.text
    state = context.user_data.get('state')

    if state == 'check_price':
        symbol = text.upper().replace('/', '')  # Normalize to BTCUSDT
        price = get_price(symbol)
        if price:
            await update.message.reply_text(f"🔍 **Harga {symbol}:** ${price:.4f}", reply_markup=back_button(), parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ **Coin tidak ditemukan.** Coba lagi.", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data.pop('state', None)
    elif state == 'trade_type':
        if text.lower() in ['beli', 'jual']:
            context.user_data['trade_type'] = text.lower()
            if text.lower() == 'beli':
                symbols = get_all_usdt_symbols()
                symbol_list = "\n".join(symbols[:20]) + "\n... (dan banyak lagi)"
                await update.message.reply_text(f"📜 **Daftar Coin Tersedia (USDT pairs):** \n{symbol_list}\n\n**Masukkan nama coin** (contoh: BTCUSDT):", reply_markup=back_button(), parse_mode='Markdown')
                context.user_data['state'] = 'trade_symbol'
            elif text.lower() == 'jual':
                holdings_list = "\n".join(data['holdings'].keys()) if data['holdings'] else "Tidak ada holdings."
                await update.message.reply_text(f"📜 **Holdings Anda untuk Dijual:**\n{holdings_list}\n\n**Masukkan nama coin** dari holdings (contoh: BTCUSDT):", reply_markup=back_button(), parse_mode='Markdown')
                context.user_data['state'] = 'trade_symbol'
        else:
            await update.message.reply_text("❌ **Pilih 'beli' atau 'jual' saja.**", reply_markup=back_button(), parse_mode='Markdown')
    elif state == 'trade_symbol':
        symbol = text.upper().replace('/', '')
        if (context.user_data['trade_type'] == 'beli' and symbol in get_all_usdt_symbols()) or \
           (context.user_data['trade_type'] == 'jual' and symbol in data['holdings']):
            context.user_data['symbol'] = symbol
            if context.user_data['trade_type'] == 'jual':
                await update.message.reply_text("💵 **Masukkan jumlah dalam $** atau ketik *'all'* untuk jual semua:", reply_markup=back_button(), parse_mode='Markdown')
            else:
                await update.message.reply_text("💵 **Masukkan jumlah dalam $** untuk dibeli:", reply_markup=back_button(), parse_mode='Markdown')
            context.user_data['state'] = 'trade_amount'
        else:
            await update.message.reply_text("❌ **Coin tidak ditemukan atau tidak di holdings.** Coba lagi.", reply_markup=back_button(), parse_mode='Markdown')
    elif state == 'trade_amount':
        symbol = context.user_data['symbol']
        price = get_price(symbol)
        if not price:
            await update.message.reply_text("❌ **Gagal mendapatkan harga.** Coba lagi.", reply_markup=back_button(), parse_mode='Markdown')
            context.user_data.pop('state', None)
            return
        trade_type = context.user_data['trade_type']
        try:
            if text.lower() == 'all' and trade_type == 'jual':
                if symbol not in data['holdings']:
                    raise ValueError("Tidak ada holding.")
                holding = data['holdings'][symbol]
                amount_coin = holding['amount']
                amount_usd = amount_coin * price
                data['balance'] += amount_usd
                del data['holdings'][symbol]
                save_data(data)
                await update.message.reply_text(f"✅ **Jual SEMUA {amount_coin:.4f} {symbol}** seharga ${amount_usd:.4f}", reply_markup=back_button(), parse_mode='Markdown')
            else:
                amount_usd = float(text)
                amount_coin = amount_usd / price
                if trade_type == 'beli':
                    if amount_usd > data['balance']:
                        raise ValueError("Balance tidak cukup.")
                    if symbol in data['holdings']:
                        holding = data['holdings'][symbol]
                        total_cost = holding['amount'] * holding['avg_price'] + amount_usd
                        total_amount = holding['amount'] + amount_coin
                        avg_price = total_cost / total_amount
                        holding['amount'] = total_amount
                        holding['avg_price'] = avg_price
                    else:
                        data['holdings'][symbol] = {'amount': amount_coin, 'avg_price': price, 'take_profit': None, 'stop_loss': None}
                    data['balance'] -= amount_usd
                    save_data(data)
                    await update.message.reply_text(f"✅ **Beli {amount_coin:.4f} {symbol}** seharga ${amount_usd:.4f}", reply_markup=back_button(), parse_mode='Markdown')
                elif trade_type == 'jual':
                    if symbol not in data['holdings'] or amount_coin > data['holdings'][symbol]['amount']:
                        raise ValueError("Holding tidak cukup.")
                    holding = data['holdings'][symbol]
                    holding['amount'] -= amount_coin
                    data['balance'] += amount_usd
                    if holding['amount'] <= 0:
                        del data['holdings'][symbol]
                    save_data(data)
                    await update.message.reply_text(f"✅ **Jual {amount_coin:.4f} {symbol}** seharga ${amount_usd:.4f}", reply_markup=back_button(), parse_mode='Markdown')
        except ValueError as e:
            await update.message.reply_text(f"❌ **Error:** {str(e)}", reply_markup=back_button(), parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ **Input tidak valid.** Coba lagi.", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data.pop('state', None)
        context.user_data.pop('trade_type', None)
        context.user_data.pop('symbol', None)
    elif state == 'set_alert':
        try:
            parts = text.split()
            symbol = parts[0].upper().replace('/', '')
            price_target = float(parts[1])
            direction = parts[2].lower()
            if direction not in ['above', 'below']:
                raise ValueError
            data['alerts'].append({'symbol': symbol, 'price': price_target, 'direction': direction})
            save_data(data)
            await update.message.reply_text(f"🔔 **Alert disetel untuk {symbol}** {direction} ${price_target:.4f}", reply_markup=back_button(), parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ **Format salah.** Contoh: BTCUSDT 60000 above", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data.pop('state', None)
    elif state == 'set_tp_sl_type':
        if text.lower() in ['tp', 'sl']:
            context.user_data['tp_sl_type'] = text.lower()
            holdings_list = "\n".join(data['holdings'].keys()) if data['holdings'] else "Tidak ada holdings."
            await update.message.reply_text(f"📜 **Holdings Anda:**\n{holdings_list}\n\n**Masukkan nama coin** (contoh: BTCUSDT):", reply_markup=back_button(), parse_mode='Markdown')
            context.user_data['state'] = 'set_tp_sl_symbol'
        else:
            await update.message.reply_text("❌ **Pilih 'tp' atau 'sl' saja.**", reply_markup=back_button(), parse_mode='Markdown')
    elif state == 'set_tp_sl_symbol':
        symbol = text.upper().replace('/', '')
        if symbol in data['holdings']:
            context.user_data['symbol'] = symbol
            await update.message.reply_text("💲 **Masukkan harga target** (atau 0 untuk batal):", reply_markup=back_button(), parse_mode='Markdown')
            context.user_data['state'] = 'set_tp_sl_price'
        else:
            await update.message.reply_text("❌ **Coin tidak ditemukan di holdings.**", reply_markup=back_button(), parse_mode='Markdown')
    elif state == 'set_tp_sl_price':
        try:
            price_target = float(text)
            symbol = context.user_data['symbol']
            tp_sl_type = context.user_data['tp_sl_type']
            if tp_sl_type == 'tp':
                data['holdings'][symbol]['take_profit'] = price_target if price_target > 0 else None
            elif tp_sl_type == 'sl':
                data['holdings'][symbol]['stop_loss'] = price_target if price_target > 0 else None
            save_data(data)
            label = "Take-Profit" if tp_sl_type == 'tp' else "Stop-Loss"
            msg = f"✅ **{label} disetel untuk {symbol}** di ${price_target:.4f}" if price_target > 0 else f"✅ **{label} dibatalkan untuk {symbol}**"
            await update.message.reply_text(msg, reply_markup=back_button(), parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ **Input tidak valid.**", reply_markup=back_button(), parse_mode='Markdown')
        context.user_data.pop('state', None)
        context.user_data.pop('tp_sl_type', None)
        context.user_data.pop('symbol', None)

# Alert and TP/SL checker thread
def checker(bot):
    while True:
        if data['chat_id']:
            # Check alerts
            for alert in data['alerts'][:]:
                current_price = get_price(alert['symbol'])
                if current_price:
                    if (alert['direction'] == 'above' and current_price > alert['price']) or \
                       (alert['direction'] == 'below' and current_price < alert['price']):
                        bot.send_message(data['chat_id'], f"🔔 **Alert triggered: {alert['symbol']}** {alert['direction']} ${alert['price']:.4f} | Current: ${current_price:.4f}", parse_mode='Markdown')
                        data['alerts'].remove(alert)
                        save_data(data)
            # Check TP/SL
            for symbol in list(data['holdings'].keys()):
                info = data['holdings'][symbol]
                current_price = get_price(symbol)
                if current_price:
                    if info['take_profit'] and current_price >= info['take_profit']:
                        amount_coin = info['amount']
                        amount_usd = amount_coin * current_price
                        data['balance'] += amount_usd
                        del data['holdings'][symbol]
                        save_data(data)
                        bot.send_message(data['chat_id'], f"📈 **Take-Profit triggered untuk {symbol}:** Jual semua pada ${current_price:.4f} | Profit: ${amount_usd:.4f}", parse_mode='Markdown')
                    elif info['stop_loss'] and current_price <= info['stop_loss']:
                        amount_coin = info['amount']
                        amount_usd = amount_coin * current_price
                        data['balance'] += amount_usd
                        del data['holdings'][symbol]
                        save_data(data)
                        bot.send_message(data['chat_id'], f"📉 **Stop-Loss triggered untuk {symbol}:** Jual semua pada ${current_price:.4f} | Amount: ${amount_usd:.4f}", parse_mode='Markdown')
        time.sleep(30)  # Check every 30 seconds for more real-time feel

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message))

    # Start checker in thread
    threading.Thread(target=checker, args=(application.bot,), daemon=True).start()

    application.run_polling()