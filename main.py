import os, sys, discord, yt_dlp, asyncio, spotipy, requests, json
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from discord.ext import commands
load_dotenv()

TK_DISCORD = os.getenv("TK_DISCORD")
SPOTIPY_CLIENT_ID = os.getenv("SPTFY")
SPOTIPY_CLIENT_SECRET = os.getenv("SPTFYS")

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
queues = {}
current_track = {}
last_player_message = {}
playlist_tasks = {}
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIPY_CLIENT_ID, 
        client_secret=SPOTIPY_CLIENT_SECRET))

def create_queue_embed(guild_id: int) -> discord.Embed:
    curr = current_track.get(guild_id)
    songs_list = list(queues[guild_id]._queue) if guild_id in queues else []
    total_in_queue = len(songs_list)

    embed = discord.Embed(
        title="📜 Lista de Reproducción",
        color=0x9B59B6
    )

    if curr:
        c_dur = curr.get('duration') or 0
        c_time = f"{c_dur // 60:02d}:{c_dur % 60:02d}" if c_dur > 0 else "EN VIVO"
        embed.add_field(
            name="🎧 Sonando Ahora",
            value=f"**[{curr['title']}]({curr['webpage_url']})** `[{c_time}]`",
            inline=False
        )

    if songs_list:
        lines = []
        for i, song in enumerate(songs_list[:10]):
            dur = song.get('duration') or 0
            dur_str = f"{dur // 60:02d}:{dur % 60:02d}" if dur > 0 else "EN VIVO"
            title = song['title']
            if len(title) > 42:
                title = f"{title[:39]}..."
            lines.append(f"`{i+1:02d}.` **[{title}]({song['webpage_url']})** `[{dur_str}]`")

        embed.add_field(
            name="A continuación",
            value="\n".join(lines),
            inline=False
        )
    else:
        embed.add_field(
            name="A continuación",
            value="*No hay más pistas en espera.*",
            inline=False
        )

    total_duration = sum((s.get('duration') or 0) for s in songs_list)
    mins, secs = divmod(total_duration, 60)
    hours, mins = divmod(mins, 60)
    time_str = f"{hours}h {mins:02d}m" if hours > 0 else f"{mins:02d}:{secs:02d}"

    footer_text = f"Pistas en espera: {total_in_queue} • Duración estimada: {time_str}"
    if total_in_queue > 10:
        footer_text = f"Mostrando 10 de {total_in_queue} pistas • Duración: {time_str}"
    embed.set_footer(text=footer_text)

    return embed

bot = commands.Bot(command_prefix="!", intents=intents)

class MusicControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # --- FILA 0 (4 botones) ---
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
            
    # --- FILA 1 (4 botones) ---
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
        
        bg_task = playlist_tasks.get(guild_id)
        has_task = bg_task is not None and not bg_task.done()
        has_queue = guild_id in queues and not queues[guild_id].empty()
        is_playing = client_voice is not None and (client_voice.is_playing() or client_voice.is_paused())

        if is_playing or has_queue or has_task:
            if bg_task and not bg_task.done():
                bg_task.cancel()
                playlist_tasks[guild_id] = None

            queues[guild_id] = asyncio.Queue()
            current_track[guild_id] = None
            loop_states[guild_id] = False

            if client_voice and (client_voice.is_playing() or client_voice.is_paused()):
                client_voice.stop()

            await interaction.response.send_message("Reproducción detenida, lista vaciada y tareas canceladas.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay ninguna pista activa ni en lista.", ephemeral=True)
        
    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary, emoji="📜", row=1)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild_id
        is_empty = guild_id not in queues or queues[guild_id].empty()
        curr = current_track.get(guild_id)

        if is_empty and not curr:
            await interaction.response.send_message("La lista está vacía y no hay nada sonando.", ephemeral=True)
            return

        embed = create_queue_embed(guild_id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.secondary, emoji="🗑️", row=1)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild_id
        bg_task = playlist_tasks.get(guild_id)
        has_task = bg_task is not None and not bg_task.done()
        has_queue = guild_id in queues and not queues[guild_id].empty()

        if has_queue or has_task:
            if bg_task and not bg_task.done():
                bg_task.cancel()
                playlist_tasks[guild_id] = None

            queues[guild_id] = asyncio.Queue()
            await interaction.response.send_message("Cola de espera vaciada. La canción actual continuará hasta finalizar.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay canciones en espera para limpiar.", ephemeral=True)

@bot.event
async def on_ready():
    
    print(f"Sesión establecida con éxito como: {bot.user}")
    
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id != bot.user.id:
        return
    
    if before.channel is not None and after.channel is None:
        guild_id = member.guild.id
        
        bg_task = playlist_tasks.get(guild_id)
        if bg_task and not bg_task.done():
            bg_task.cancel()
            playlist_tasks[guild_id] = None

        queues[guild_id] = asyncio.Queue()
        current_track[guild_id] = None
        loop_states[guild_id] = False

        old_msg = last_player_message.get(guild_id)
        if old_msg:
            try:
                await old_msg.delete()
            except discord.NotFound:
                pass
            last_player_message[guild_id] = None

        print(f"[AutoClean] {member.guild.name} tras abandonar la llamada")
    
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
        
    bg_task = playlist_tasks.get(guild_id)
    if bg_task and not bg_task.done():
        bg_task.cancel()
        playlist_tasks[guild_id] = None

    queues[guild_id] = asyncio.Queue()
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
        song = current_track[guild_id]
    else:
        if guild_id not in queues or queues[guild_id].empty():
            current_track[guild_id] = None
            await ctx.send("La lista de reproducción ha finalizado.")
            return
        song = queues[guild_id].get_nowait()
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
    dur_str = f"{dur // 60:02d}:{dur % 60:02d}" if dur > 0 else "EN VIVO"

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
    
async def load_spotify_playlist_background(ctx, queries, requester):
    guild_id = ctx.guild.id

    for query in queries:
        if ctx.guild.voice_client is None:
            break
        try:
            info = ytdl.extract_info(f"ytsearch1:{query}", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                first_entry = info['entries'][0]
                
                song = {
                    'url': first_entry['url'],
                    'title': first_entry.get('title', query),
                    'duration': first_entry.get('duration', 0),
                    'thumbnail': first_entry.get('thumbnail'),
                    'webpage_url': first_entry.get('webpage_url', ''),
                    'requester': requester
                }
                
                if guild_id in queues:
                    await queues[guild_id].put(song)
                    
                    client_voice = ctx.guild.voice_client
                    if client_voice and not client_voice.is_playing() and not client_voice.is_paused():
                        await play_next(ctx)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Spotify Bridge] Error buscando '{query}': {e}")
            
        await asyncio.sleep(1.5)

@bot.command()
async def play(ctx,* , search):
    if ctx.author.voice is None:
        await ctx.send("Debes estar en un canal de voz para reproducir música.")
        return
    
    if ctx.guild.voice_client is None:
        await ctx.author.voice.channel.connect()
        
    client_voice = ctx.guild.voice_client
    
    if "open.spotify.com/track/" in search:
        track_data = sp.track(search)
        query = f"{track_data['artists'][0]['name']} {track_data['name']}"
        search = f"ytsearch1:{query}"
        
    elif "open.spotify.com/playlist/" in search:
        queries = get_spotify_playlist_tracks(search)
        
        if not queries:
            await ctx.send("No se pudieron cargar las pistas de esta playlist.")
            return

        search = f"ytsearch1:{queries[0]}"

        if len(queries) > 1:
            await ctx.send(f"📥 Playlist de Spotify detectada: Cargando {len(queries)} pistas...", delete_after=8)
            task = asyncio.create_task(load_spotify_playlist_background(ctx, queries[1:], ctx.author.display_name))
            playlist_tasks[ctx.guild.id] = task
    
    if not search.startswith("http") and not search.startswith("ytsearch"):
        search = f"ytsearch1:{search}"
    
    info = ytdl.extract_info(search, download=False)
    
    if 'entries' in info:
        if not info['entries']:
            await ctx.send("No se encontró ningún resultado en YouTube para esta búsqueda.")
            return
        info = info['entries'][0]

    if not info or 'url' not in info:
        await ctx.send("No se pudo extraer el audio de la pista solicitada.")
        return

    url_stream = info['url']
    title = info.get('title', 'Canción desconocida')
    song = {'url': url_stream, 'title': title, 'duration': info.get('duration', 0),'thumbnail': info.get('thumbnail'),'webpage_url': info.get('webpage_url', search),'requester': ctx.author.display_name}
    
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = asyncio.Queue()

    if client_voice.is_playing() or client_voice.is_paused():
        await queues[ctx.guild.id].put(song)
        await ctx.send(f"Añadido a la lista: **{title}**", delete_after=6)
    else:
        await queues[ctx.guild.id].put(song)
        await play_next(ctx)
    
@bot.command()
async def stop(ctx):
    client_voice = ctx.guild.voice_client
    guild_id = ctx.guild.id
    
    if client_voice is None:
        await ctx.send("No estoy conectado a ningún canal de voz.")
        return
        
    bg_task = playlist_tasks.get(guild_id)
    has_task = bg_task is not None and not bg_task.done()
    has_queue = guild_id in queues and not queues[guild_id].empty()
    is_playing = client_voice.is_playing() or client_voice.is_paused()

    if not is_playing and not has_queue and not has_task:
        await ctx.send("No hay ninguna pista reproduciéndose ni en espera.")
        return
    
    if bg_task and not bg_task.done():
        bg_task.cancel()
        playlist_tasks[guild_id] = None

    queues[guild_id] = asyncio.Queue()
    current_track[guild_id] = None
    loop_states[guild_id] = False

    if is_playing:
        client_voice.stop()
        
    await ctx.send("Reproducción detenida, lista vaciada y tareas en segundo plano canceladas.")

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
    is_empty = guild_id not in queues or queues[guild_id].empty()
    curr = current_track.get(guild_id)
    
    if is_empty and not curr:
        await ctx.send("La lista está vacía y no hay nada sonando.")
        return

    embed = create_queue_embed(guild_id)
    await ctx.send(embed=embed)

@bot.command()
async def clear(ctx):
    guild_id = ctx.guild.id
    bg_task = playlist_tasks.get(guild_id)
    has_task = bg_task is not None and not bg_task.done()
    has_queue = guild_id in queues and not queues[guild_id].empty()

    if not has_queue and not has_task:
        await ctx.send("No hay pistas en espera para limpiar.")
        return

    if bg_task and not bg_task.done():
        bg_task.cancel()
        playlist_tasks[guild_id] = None

    queues[guild_id] = asyncio.Queue()
    await ctx.send("Cola de espera vaciada. La canción actual continuará sonando.")
    
def get_spotify_playlist_tracks(playlist_url):
    embed_url = playlist_url.replace("open.spotify.com/playlist/", "open.spotify.com/embed/playlist/")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(embed_url, headers=headers)
        if response.status_code != 200:
            return []

        start = response.text.find('__NEXT_DATA__')
        if start == -1:
            return []
            
        start = response.text.find('>', start) + 1
        end = response.text.find('</script>', start)
        
        data = json.loads(response.text[start:end])
        track_list = data['props']['pageProps']['state']['data']['entity'].get('trackList', [])
        
        return [f"{track['subtitle']} {track['title']}" for track in track_list if 'title' in track and 'subtitle' in track]
    except Exception as e:
        print(f"[Spotify Scraper] Error al obtener playlist: {e}")
        return []

if __name__ == "__main__":
    bot.run(TK_DISCORD)