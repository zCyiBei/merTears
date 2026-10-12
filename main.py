import os, sys, discord, yt_dlp, asyncio
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()

TK_DISCORD = os.getenv("TK_DISCORD")

if not TK_DISCORD:
    sys.exit("Error: Token no especificado en variables de entorno")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# Mapping
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
loop_states = {}
current_tracks = {}
queues = {}
current_track = {}
last_player_message = {}

bot = commands.Bot(command_prefix="!", intents=intents)

class MusicControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # --- FILA 0 (3 botones de flujo de audio) ---
    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        client_voice = interaction.guild.voice_client
        if client_voice and client_voice.is_playing():
            client_voice.pause()
            await interaction.response.send_message("Pausado mediante interfaz.", ephemeral=True)
        else:
            await interaction.response.send_message("No se puede pausar.", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.secondary, emoji="▶️", row=0)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        client_voice = interaction.guild.voice_client
        if client_voice and client_voice.is_paused():
            client_voice.resume()
            await interaction.response.send_message("Reanudado mediante interfaz.", ephemeral=True)
        else:
            await interaction.response.send_message("No está pausado.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️", row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        client_voice = interaction.guild.voice_client
        guild_id = interaction.guild_id
        if client_voice and (client_voice.is_playing() or client_voice.is_paused()):
            if loop_states.get(guild_id, False):
                current_track[guild_id] = None

            client_voice.stop()
            await interaction.response.send_message("Pista saltada mediante interfaz.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay nada que saltar.", ephemeral=True)
            
    # --- FILA 1 (3 botones de lista y parada) ---
    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", row=0)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild_id
        current_state = loop_states.get(guild_id, False)
        loop_states[guild_id] = not current_state
        msg = "Bucle activado para la pista actual." if loop_states[guild_id] else "Bucle desactivado."
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary, emoji="⏹️", row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        client_voice = interaction.guild.voice_client
        guild_id = interaction.guild_id
        if client_voice and (client_voice.is_playing() or client_voice.is_paused()):
            queues[guild_id] = []
            loop_states[guild_id] = False
            current_track[guild_id] = None
            client_voice.stop()
            await interaction.response.send_message("Reproducción detenida y cola vaciada.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay ninguna pista sonando.", ephemeral=True)
        
    @discord.ui.button(label="Cola", style=discord.ButtonStyle.secondary, emoji="📜", row=1)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild_id
        if guild_id not in queues or len(queues[guild_id]) == 0:
            await interaction.response.send_message("La cola está vacía.", ephemeral=True)
            return

        text_list = "**Cola de reproducción actual:**\n"
        for i, song in enumerate(queues[guild_id][:10]):
            text_list += f"{i+1}. {song['title']}\n"
        if len(queues[guild_id]) > 10:
            text_list += f"... y {len(queues[guild_id]) - 10} más en espera.\n"

        await interaction.response.send_message(text_list, ephemeral=True)

@bot.event
async def on_ready():
    
    print(f"Sesión establecida con éxito como: {bot.user}")
    
@bot.command()
async def join(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Debes estar conectado a un canal de voz.")
        return
    
    channel = ctx.author.voice.channel
    
    if ctx.guild.voice_client is not None:
        if ctx.guild.voice_client.channel == channel:
            await ctx.send("Ya me encuentro en este canal.")
            return
        else:
            await ctx.guild.voice_client.move_to(channel)
            return

    await channel.connect()
    await ctx.send(f"Conectado a {channel.name}")

@bot.command()
async def leave(ctx):
    client_voice = ctx.guild.voice_client
    
    if not client_voice:
        await ctx.send("No estoy conectado a ningún canal de voz.")
        return
    
    guild_id = ctx.guild.id
    if client_voice.is_playing() or client_voice.is_paused():
        client_voice.stop()
        
    queues[guild_id] = []
    current_track[guild_id] = None
    loop_states[guild_id] = False

    await client_voice.disconnect()
    await ctx.send("Desconectado Exitosamente.")

async def play_next(ctx):
    guild_id = ctx.guild.id
    client_voice = ctx.guild.voice_client
    
    if client_voice is None:
        return
    
    if loop_states.get(guild_id, False) and current_track.get(guild_id):
        queues[guild_id].insert(0, current_track[guild_id])
    
    if guild_id not in queues or len(queues[guild_id]) == 0:
        current_track[guild_id] = None
        await ctx.send("La cola de reproducción ha finalizado.")
        return
    
    song = queues[guild_id].pop(0)
    current_track[guild_id] = song
    
    if client_voice.is_playing() or client_voice.is_paused():
        client_voice.stop()
        await asyncio.sleep(0.5)

    source = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)

    def after_playing(error):
        if error:
            print(f"Error en streaming de audio: {error}")
        asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

    client_voice.play(source, after=after_playing)

    dur = song.get('duration') or 0
    dur_str = f"{dur // 60:02d}:{dur % 60:02d}" if dur > 0 else "🔴 EN VIVO"

    embed = discord.Embed(
        title="♫ Reproduciendo Ahora",
        description=f"**[{song['title']}]({song['webpage_url']})**",
        color=0x9B59B6
    )

    embed.set_author(
        name="merTears",
        icon_url="https://i.gifer.com/V9yP.gif"
    )

    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])

    embed.add_field(name="⏱️ Duración", value=dur_str, inline=True)
    embed.add_field(name="🗿 Pedido por", value=song.get('requester', 'Desconocido'), inline=True)

    old_msg = last_player_message.get(guild_id)
    if old_msg:
        try:
            await old_msg.delete()
        except discord.NotFound:
            pass

    new_msg = await ctx.send(embed=embed, view=MusicControls())
    last_player_message[guild_id] = new_msg

@bot.command()
async def play(ctx,* , search):
    if ctx.author.voice is None:
        await ctx.send("Debes estar en un canal de voz para reproducir música.")
        return
    
    if ctx.guild.voice_client is None:
        await ctx.author.voice.channel.connect()
        
    client_voice = ctx.guild.voice_client
    
    if not search.startswith("http"):
        search = f"ytsearch:{search}"
    
    info = ytdl.extract_info(search, download=False)
    if 'entries' in info:
        info = info['entries'][0]
        
    url_stream = info['url']
    title = info.get('title', 'Canción desconocida')
    song = {'url': url_stream, 'title': title, 'duration': info.get('duration', 0),'thumbnail': info.get('thumbnail'),'webpage_url': info.get('webpage_url', search),'requester': ctx.author.display_name}
    
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []

    if client_voice.is_playing() or client_voice.is_paused():
        queues[ctx.guild.id].append(song)
        # Se borra solo a los 6 segundos para no desfasar el chat
        await ctx.send(f" Añadido a la cola: **{title}**", delete_after=6)
    else:
        queues[ctx.guild.id].append(song)
        await play_next(ctx)
    
@bot.command()
async def stop(ctx):
    client_voice = ctx.guild.voice_client
    
    if client_voice is None:
        await ctx.send("No estoy conectado a ningún canal de voz.")
        return
        
    if not client_voice.is_playing() and not client_voice.is_paused():
        await ctx.send("No hay ninguna pista reproduciéndose actualmente.")
        return
    
    client_voice.stop()
    await ctx.send("Reproducción detenida.")
    
@bot.command()
async def pause(ctx):
    client_voice = ctx.guild.voice_client
    
    if client_voice is None:
        await ctx.send("No estoy conectado a un canal de voz.")
        return
    
    if not client_voice.is_playing():
        await ctx.send("No hay ninguna pista reproduciéndose para pausar.")
        return
    
    client_voice.pause()
    await ctx.send("Reproducción pausada.")
    
@bot.command()
async def resume(ctx):
        client_voice = ctx.guild.voice_client
        
        if client_voice is None:
            await ctx.send("No estoy conectado a un canal de voz.")
            return
        
        if not client_voice.is_paused():
            await ctx.send("La reproducción no está pausada.")
            return
        
        client_voice.resume()
        await ctx.send("Reproducción reanudada.")
        
@bot.command()
async def loop(ctx):
    guild_id = ctx.guild.id

    current_state = loop_states.get(guild_id, False)
    new_state = not current_state
    loop_states[guild_id] = new_state
    
    if new_state is True:
        await ctx.send("Bucle activado para la pista actual.")
        
    else:
        await ctx.send("Bucle desactivado.")
        
@bot.command()
async def queue(ctx):
    guild_id = ctx.guild.id
    
    if guild_id not in queues or len(queues[guild_id]) == 0:
        await ctx.send("La cola esta vacía.")
        return
    
    text_list = "**Cola de reproducción actual:**\n"
    for i, song in enumerate(queues[guild_id]):
        text_list += f"{i+1}. {song['title']}\n"
        if i == 9:
            text_list += "... y más canciones en espera.\n"
            break
        
    await ctx.send(text_list)
        
    
if __name__ == "__main__":
    bot.run(TK_DISCORD)