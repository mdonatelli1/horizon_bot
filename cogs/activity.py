from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Config
from database.models import Activity, Registration


class WeaponConfigModal(discord.ui.Modal):
    """Modal pour configurer les armes de chaque classe"""

    def __init__(
        self,
        title: str,
        event_datetime: datetime,
        leader: discord.Member,
        ping_role: discord.Role,
        cog,
        activity_id: int = None,
        current_config: dict = None,
        edit_mode: bool = False,
    ):
        super().__init__(title="⚔️ Configuration des armes")
        self.activity_title = title
        self.event_datetime = event_datetime
        self.leader = leader
        self.ping_role = ping_role
        self.cog = cog
        self.activity_id = activity_id
        self.edit_mode = edit_mode

        def format_role(role: str):
            if not current_config:
                return None

            role_config = current_config.get(role)
            if not role_config:
                return None

            return ", ".join(
                f"{weapon}:{count}" for weapon, count in role_config.items()
            )

        # Champs de la modal
        self.tank_field = discord.ui.TextInput(
            label="🛡️ Tank",
            placeholder="Greataxe:2, Mace:1",
            default=format_role("Tank"),
            max_length=200,
            required=True,
        )

        self.healer_field = discord.ui.TextInput(
            label="💚 Healer",
            placeholder="Holy Staff:2, Nature Staff:1",
            default=format_role("Healer"),
            max_length=200,
            required=True,
        )

        self.dps_field = discord.ui.TextInput(
            label="⚔️ DPS",
            placeholder="Bow:3, Crossbow:2, Fire Staff:1",
            default=format_role("DPS"),
            max_length=200,
            required=True,
        )

        self.add_item(self.tank_field)
        self.add_item(self.healer_field)
        self.add_item(self.dps_field)

    def parse_weapons(self, text: str) -> dict:
        """Parser le texte des armes en dictionnaire"""
        result = {}
        try:
            weapons = [w.strip() for w in text.split(",")]
            for weapon in weapons:
                if ":" in weapon:
                    name, count = weapon.rsplit(":", 1)
                    name = name.strip()
                    count = int(count.strip())
                    if count > 0:
                        result[name] = count
        except:
            raise ValueError("Format invalide")
        return result

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parser les configurations
            roles_config = {
                "Tank": self.parse_weapons(self.tank_field.value),
                "Healer": self.parse_weapons(self.healer_field.value),
                "DPS": self.parse_weapons(self.dps_field.value),
            }

            # Vérifier qu'il y a au moins une arme par classe
            if not all(roles_config.values()):
                await interaction.response.send_message(
                    "❌ Chaque classe doit avoir au moins une arme configurée.",
                    ephemeral=True,
                )
                return

            if self.edit_mode:
                # Mode édition : mettre à jour l'activité existante
                await self.update_existing_activity(interaction, roles_config)
            else:
                # Mode création : créer une nouvelle activité
                await self.create_new_activity(interaction, roles_config)

        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Erreur de format. Utilisez le format : `NomArme:Nombre`\n"
                f"Exemple : `Greataxe:2, Mace:1`\n\n"
                f"Détails : {str(e)}",
                ephemeral=True,
            )

    async def create_new_activity(
        self, interaction: discord.Interaction, roles_config: dict
    ):
        """Créer une nouvelle activité avec la config des armes"""
        await interaction.response.defer(ephemeral=True)

        # Créer l'embed de l'activité
        embed = self.cog.create_activity_embed(
            self.activity_title, self.event_datetime, self.leader, roles_config
        )

        # Préparer le contenu du message avec le ping du rôle
        role = self.ping_role
        if role:
            if role.name in ["@everyone", "@here"]:
                mention = role.name
            else:
                mention = role.mention
        else:
            mention = None

        # CORRECTION: Envoyer l'embed ET le ping dans le même message
        content = (
            f"📢 {mention} — Nouvelle activité créée : **{self.activity_title}**"
            if mention
            else None
        )

        # Envoyer le message dans le canal
        message = await interaction.channel.send(content=content, embed=embed)

        # Créer un thread pour les inscriptions
        thread = await message.create_thread(
            name=f"📋 {self.activity_title}", auto_archive_duration=1440
        )

        # Sauvegarder dans la base de données
        session = self.cog.db.get_session()
        try:
            activity = Activity(
                message_id=str(message.id),
                thread_id=str(thread.id),
                channel_id=str(interaction.channel.id),
                guild_id=str(interaction.guild.id),
                title=self.activity_title,
                leader=str(self.leader.id),
                event_date=self.event_datetime,
                ping_role_id=str(self.ping_role.id),
                roles_config=roles_config,
                reminders=Config.DEFAULT_REMINDER_MINUTES,
            )
            session.add(activity)
            session.commit()

            # Compter le nombre total de slots
            total_slots = sum(
                sum(weapons.values()) for weapons in roles_config.values()
            )

            await interaction.followup.send(
                f"✅ Activité **{self.activity_title}** créée avec succès !\n"
                f"👑 Leader : {self.leader.mention}\n"
                f"📢 Rôle à ping : {self.ping_role.mention}\n"
                f"🎯 Slots disponibles : **{total_slots}**\n"
                f"💬 Thread d'inscription : {thread.mention}\n\n"
                f"*Les joueurs peuvent s'inscrire avec `/party join <slot>` dans le thread.*",
                ephemeral=True,
            )

        finally:
            session.close()

    async def update_existing_activity(
        self, interaction: discord.Interaction, roles_config: dict
    ):
        """Mettre à jour la configuration des armes d'une activité existante"""
        await interaction.response.defer(ephemeral=True)

        session = self.cog.db.get_session()
        try:
            # Récupérer l'activité
            activity = session.query(Activity).filter_by(id=self.activity_id).first()

            if not activity:
                await interaction.followup.send(
                    "❌ Activité introuvable.", ephemeral=True
                )
                return

            # CORRECTION: Recalculer les inscriptions basées sur rôle/arme plutôt que sur slot_number
            registrations = (
                session.query(Registration).filter_by(activity_id=activity.id).all()
            )

            # Créer un mapping des inscriptions actuelles par (role, weapon, index)
            current_mapping = {}
            for reg in registrations:
                key = (reg.role_name, reg.weapon)
                if key not in current_mapping:
                    current_mapping[key] = []
                current_mapping[key].append(reg)

            # Calculer les nouveaux slots et réassigner
            new_slot = 1
            registrations_to_keep = []
            registrations_to_delete = []

            for role_name, weapons in roles_config.items():
                for weapon, count in weapons.items():
                    key = (role_name, weapon)
                    existing_regs = current_mapping.get(key, [])

                    # Garder seulement le nombre de slots disponibles
                    for i in range(count):
                        if i < len(existing_regs):
                            # Réassigner le slot_number
                            existing_regs[i].slot_number = new_slot
                            registrations_to_keep.append(existing_regs[i])
                        new_slot += 1

                    # Marquer les inscriptions en trop pour suppression
                    if len(existing_regs) > count:
                        registrations_to_delete.extend(existing_regs[count:])

            # Supprimer les inscriptions qui n'ont plus de place
            for reg in registrations_to_delete:
                session.delete(reg)

            # Mettre à jour la configuration
            activity.roles_config = roles_config
            session.commit()

            # Mettre à jour l'embed
            await self.cog.update_activity_embed(activity, session)

            new_total_slots = sum(
                sum(weapons.values()) for weapons in roles_config.values()
            )

            message = f"✅ Configuration des armes mise à jour !\n🎯 Nouveaux slots : **{new_total_slots}**\n"

            if registrations_to_delete:
                message += f"⚠️ {len(registrations_to_delete)} inscription(s) supprimée(s) (plus de slots disponibles pour ce rôle/arme)"

            await interaction.followup.send(message, ephemeral=True)

        finally:
            session.close()


class PartyGroup(app_commands.Group):
    """Groupe de commandes /party"""

    def __init__(self):
        super().__init__(name="party", description="Gestion des activités de guilde")


class ActivityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    # Groupe de commandes /party
    party = PartyGroup()

    @party.command(name="create", description="Créer une nouvelle activité de guilde")
    @app_commands.describe(
        title="Titre de l'activité",
        date="Date (format: JJ/MM/AAAA)",
        time="Heure (format: HH:MM)",
        leader="Leader de l'activité",
        ping_role="Rôle à mentionner lors des rappels",
    )
    async def party_create(
        self,
        interaction: discord.Interaction,
        title: str,
        date: str,
        time: str,
        leader: discord.Member,
        ping_role: discord.Role,
    ):
        try:
            # Parser la date et l'heure
            event_datetime = datetime.strptime(f"{date} {time}", "%d/%m/%Y %H:%M")

            # Vérifier que la date est dans le futur
            if event_datetime <= datetime.now():
                await interaction.response.send_message(
                    "❌ La date de l'activité doit être dans le futur.",
                    ephemeral=True,
                )
                return

            # Afficher la modal pour configurer les armes
            modal = WeaponConfigModal(
                title=title,
                event_datetime=event_datetime,
                leader=leader,
                ping_role=ping_role,
                cog=self,
            )
            await interaction.response.send_modal(modal)

        except ValueError:
            await interaction.response.send_message(
                "❌ Format de date/heure invalide. Utilisez **JJ/MM/AAAA** pour la date et **HH:MM** pour l'heure.\n"
                "Exemple : `31/01/2026` et `20:00`",
                ephemeral=True,
            )

    @party.command(name="edit", description="Modifier une activité existante")
    @app_commands.describe(
        title="Nouveau titre (laisser vide pour ne pas changer)",
        date="Nouvelle date (format: JJ/MM/AAAA, laisser vide pour ne pas changer)",
        time="Nouvelle heure (format: HH:MM, laisser vide pour ne pas changer)",
        leader="Nouveau leader (laisser vide pour ne pas changer)",
        ping_role="Nouveau rôle à ping (laisser vide pour ne pas changer)",
    )
    async def party_edit(
        self,
        interaction: discord.Interaction,
        title: str = None,
        date: str = None,
        time: str = None,
        leader: discord.Member = None,
        ping_role: discord.Role = None,
    ):
        # Vérifier qu'on est dans un thread d'activité
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "❌ Cette commande doit être utilisée dans le thread d'une activité.",
                ephemeral=True,
            )
            return

        session = self.db.get_session()
        try:
            # Récupérer l'activité
            activity = (
                session.query(Activity)
                .filter_by(thread_id=str(interaction.channel.id))
                .first()
            )

            if not activity:
                await interaction.response.send_message(
                    "❌ Aucune activité trouvée pour ce thread.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Vérifier si au moins un paramètre a été fourni
            if not any([title, date, time, leader, ping_role]):
                await interaction.followup.send(
                    "❌ Veuillez spécifier au moins un paramètre à modifier.",
                    ephemeral=True,
                )
                return

            # Mettre à jour les champs
            changes = []

            if title:
                activity.title = title
                changes.append(f"Titre : **{title}**")

            if date or time:
                try:
                    current_date = activity.event_date.strftime("%d/%m/%Y")
                    current_time = activity.event_date.strftime("%H:%M")

                    new_date = date if date else current_date
                    new_time = time if time else current_time

                    event_datetime = datetime.strptime(
                        f"{new_date} {new_time}", "%d/%m/%Y %H:%M"
                    )

                    if event_datetime <= datetime.now():
                        await interaction.followup.send(
                            "❌ La nouvelle date doit être dans le futur.",
                            ephemeral=True,
                        )
                        return

                    activity.event_date = event_datetime
                    changes.append(f"Date/Heure : **{new_date} à {new_time}**")

                except ValueError:
                    await interaction.followup.send(
                        "❌ Format de date/heure invalide.", ephemeral=True
                    )
                    return

            if leader:
                activity.leader = str(leader.id)
                changes.append(f"Leader : {leader.mention}")

            if ping_role:
                activity.ping_role_id = str(ping_role.id)
                changes.append(f"Rôle à ping : {ping_role.mention}")

            session.commit()

            # Mettre à jour l'embed
            await self.update_activity_embed(activity, session)

            await interaction.followup.send(
                "✅ Activité mise à jour :\n" + "\n".join(f"• {c}" for c in changes),
                ephemeral=True,
            )

        finally:
            session.close()

    @party.command(name="weapons", description="Modifier la configuration des armes")
    async def party_weapons(self, interaction: discord.Interaction):
        # Vérifier qu'on est dans un thread d'activité
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "❌ Cette commande doit être utilisée dans le thread d'une activité.",
                ephemeral=True,
            )
            return

        session = self.db.get_session()
        try:
            # Récupérer l'activité
            activity = (
                session.query(Activity)
                .filter_by(thread_id=str(interaction.channel.id))
                .first()
            )

            if not activity:
                await interaction.response.send_message(
                    "❌ Aucune activité trouvée pour ce thread.", ephemeral=True
                )
                return

            # Afficher la modal avec la configuration actuelle
            modal = WeaponConfigModal(
                title=activity.title,
                event_datetime=activity.event_date,
                leader=None,  # On garde le leader actuel
                ping_role=None,  # On garde le rôle actuel
                cog=self,
                activity_id=activity.id,
                current_config=activity.roles_config,
                edit_mode=True,
            )
            await interaction.response.send_modal(modal)

        finally:
            session.close()

    @party.command(name="delete", description="Supprimer une activité")
    async def party_delete(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Vérifier qu'on est dans un thread d'activité
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.followup.send(
                "❌ Cette commande doit être utilisée dans le thread d'une activité.",
                ephemeral=True,
            )
            return

        session = self.db.get_session()
        try:
            # Récupérer l'activité
            activity = (
                session.query(Activity)
                .filter_by(thread_id=str(interaction.channel.id))
                .first()
            )

            if not activity:
                await interaction.followup.send(
                    "❌ Aucune activité trouvée pour ce thread.", ephemeral=True
                )
                return

            # Récupérer les informations avant suppression
            activity_title = activity.title
            message_id = int(activity.message_id)
            channel_id = int(activity.channel_id)

            # Supprimer de la base de données
            session.delete(activity)
            session.commit()

            # Supprimer le message d'activité
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
            except:
                pass

            await interaction.followup.send(
                f"✅ L'activité **{activity_title}** a été supprimée.",
                ephemeral=True,
            )

            # Archiver le thread
            try:
                await interaction.channel.edit(archived=True)
            except:
                pass

        finally:
            session.close()

    @party.command(name="join", description="Rejoindre un slot d'activité")
    @app_commands.describe(slot="Numéro du slot à rejoindre")
    async def party_join(self, interaction: discord.Interaction, slot: int):
        await interaction.response.defer(ephemeral=True)

        # Vérifier qu'on est dans un thread d'activité
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.followup.send(
                "❌ Cette commande doit être utilisée dans le thread d'une activité.",
                ephemeral=True,
            )
            return

        session = self.db.get_session()
        try:
            # Récupérer l'activité
            activity = (
                session.query(Activity)
                .filter_by(thread_id=str(interaction.channel.id))
                .first()
            )

            if not activity:
                await interaction.followup.send(
                    "❌ Aucune activité trouvée pour ce thread.", ephemeral=True
                )
                return

            # Vérifier que l'utilisateur n'est pas déjà inscrit
            existing_registration = (
                session.query(Registration)
                .filter_by(activity_id=activity.id, user_id=str(interaction.user.id))
                .first()
            )

            if existing_registration:
                await interaction.followup.send(
                    f"❌ Vous êtes déjà inscrit sur le slot {existing_registration.slot_number}.\n"
                    f"Utilisez `/party leave` pour vous désinscrire d'abord.",
                    ephemeral=True,
                )
                return

            # Trouver le rôle et l'arme correspondants au slot
            current_slot = 1
            target_role = None
            target_weapon = None

            for role_name, weapons in activity.roles_config.items():
                for weapon, count in weapons.items():
                    if current_slot <= slot < current_slot + count:
                        target_role = role_name
                        target_weapon = weapon
                        break
                    current_slot += count
                if target_role:
                    break

            if not target_role:
                await interaction.followup.send(
                    f"❌ Le slot {slot} n'existe pas.", ephemeral=True
                )
                return

            # Vérifier que le slot n'est pas déjà pris
            existing_slot = (
                session.query(Registration)
                .filter_by(activity_id=activity.id, slot_number=slot)
                .first()
            )

            if existing_slot:
                await interaction.followup.send(
                    f"❌ Le slot {slot} est déjà pris.", ephemeral=True
                )
                return

            # Créer l'inscription
            registration = Registration(
                activity_id=activity.id,
                user_id=str(interaction.user.id),
                role_name=target_role,
                weapon=target_weapon,
                slot_number=slot,
            )
            session.add(registration)
            session.commit()

            # Mettre à jour l'embed
            await self.update_activity_embed(activity, session)

            await interaction.followup.send(
                f"✅ Vous êtes inscrit sur le slot **{slot}** ({target_role} - {target_weapon}) !",
                ephemeral=True,
            )

        finally:
            session.close()

    @party.command(name="leave", description="Quitter un slot d'activité")
    async def party_leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Vérifier qu'on est dans un thread d'activité
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.followup.send(
                "❌ Cette commande doit être utilisée dans le thread d'une activité.",
                ephemeral=True,
            )
            return

        session = self.db.get_session()
        try:
            # Récupérer l'activité
            activity = (
                session.query(Activity)
                .filter_by(thread_id=str(interaction.channel.id))
                .first()
            )

            if not activity:
                await interaction.followup.send(
                    "❌ Aucune activité trouvée pour ce thread.", ephemeral=True
                )
                return

            # Vérifier que l'utilisateur est inscrit
            registration = (
                session.query(Registration)
                .filter_by(activity_id=activity.id, user_id=str(interaction.user.id))
                .first()
            )

            if not registration:
                await interaction.followup.send(
                    "❌ Vous n'êtes pas inscrit à cette activité.", ephemeral=True
                )
                return

            # Sauvegarder les infos avant suppression
            slot_number = registration.slot_number
            role_name = registration.role_name
            weapon = registration.weapon

            # Supprimer l'inscription
            session.delete(registration)
            session.commit()

            # Mettre à jour l'embed
            await self.update_activity_embed(activity, session)

            await interaction.followup.send(
                f"✅ Vous avez quitté le slot **{slot_number}** ({role_name} - {weapon}).",
                ephemeral=True,
            )

        finally:
            session.close()

    @party.command(
        name="reset", description="Retirer un joueur d'un slot (admin/leader)"
    )
    @app_commands.describe(user="Joueur à retirer de l'activité")
    async def party_reset(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        if not isinstance(interaction.channel, discord.Thread):
            await interaction.followup.send(
                "❌ Cette commande doit être utilisée dans le thread d'une activité.",
                ephemeral=True,
            )
            return

        session = self.db.get_session()
        try:
            activity = (
                session.query(Activity)
                .filter_by(thread_id=str(interaction.channel.id))
                .first()
            )

            if not activity:
                await interaction.followup.send(
                    "❌ Aucune activité trouvée pour ce thread.",
                    ephemeral=True,
                )
                return

            registration = (
                session.query(Registration)
                .filter_by(activity_id=activity.id, user_id=str(user.id))
                .first()
            )

            if not registration:
                await interaction.followup.send(
                    f"❌ {user.mention} n'est pas inscrit à cette activité.",
                    ephemeral=True,
                )
                return

            slot = registration.slot_number
            role = registration.role_name
            weapon = registration.weapon

            session.delete(registration)
            session.commit()

            await self.update_activity_embed(activity, session)

            await interaction.followup.send(
                f"✅ {user.mention} a été retiré du slot **{slot}** ({role} - {weapon}).",
                ephemeral=True,
            )

        finally:
            session.close()

    def create_activity_embed(self, title, event_date, leader, roles_config):
        """Créer l'embed d'affichage de l'activité"""
        embed = discord.Embed(title=title, color=Config.COLOR_PRIMARY)

        if leader is None:
            leader_value = "—"
        elif isinstance(leader, discord.Member):
            leader_value = f"<@{leader.id}>"
        else:
            leader_value = f"<@{leader}>"

        # Leader
        embed.add_field(
            name="👑 Leader",
            value=leader_value,
            inline=True,
        )

        # Date & Heure
        embed.add_field(
            name="📅 Date & Heure",
            value=event_date.strftime("%d/%m/%Y à %H:%M"),
            inline=True,
        )

        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # Affichage des slots par rôle
        slot_counter = 1
        for role_name, weapons in roles_config.items():
            field_value = ""
            for weapon, count in weapons.items():
                for i in range(count):
                    field_value += f"`{slot_counter}.` {weapon} - *Libre*\n"
                    slot_counter += 1

            # Emojis par rôle
            role_emoji = {"Tank": "🛡️", "Healer": "💚", "DPS": "⚔️"}.get(role_name, "🔹")

            embed.add_field(
                name=f"{role_emoji} {role_name}", value=field_value, inline=False
            )

        embed.set_footer(
            text="💡 Utilisez /party join <slot> pour vous inscrire | /party leave pour partir"
        )

        return embed

    def format_timedelta(self, td):
        """Formater un timedelta en format lisible"""
        if td.total_seconds() < 0:
            return "En cours"

        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}j")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}min")

        return " ".join(parts) if parts else "Imminent !"

    async def update_activity_embed(self, activity, session):
        """Mettre à jour l'embed avec les inscriptions actuelles"""
        # Récupérer toutes les inscriptions
        registrations = (
            session.query(Registration).filter_by(activity_id=activity.id).all()
        )

        slots_taken = {reg.slot_number: reg for reg in registrations}

        # Récupérer le message
        channel = self.bot.get_channel(int(activity.channel_id))
        if not channel:
            return

        try:
            message = await channel.fetch_message(int(activity.message_id))
        except:
            return

        embed = message.embeds[0]

        # Mettre à jour les champs de slots
        slot_counter = 1
        field_index = 3  # Leader, Date & Heure, Spacer

        for role_name, weapons in activity.roles_config.items():
            field_value = ""
            for weapon, count in weapons.items():
                for i in range(count):
                    if slot_counter in slots_taken:
                        reg = slots_taken[slot_counter]
                        user = f"<@{reg.user_id}>"
                        field_value += f"`{slot_counter}.` {weapon} - {user}\n"
                    else:
                        field_value += f"`{slot_counter}.` {weapon} - *Libre*\n"
                    slot_counter += 1

            role_emoji = {"Tank": "🛡️", "Healer": "💚", "DPS": "⚔️"}.get(role_name, "🔹")

            embed.set_field_at(
                field_index,
                name=f"{role_emoji} {role_name}",
                value=field_value,
                inline=False,
            )
            field_index += 1

        await message.edit(embed=embed)

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Vérifier les rappels d'activités"""
        session = self.db.get_session()
        try:
            now = datetime.now()
            activities = (
                session.query(Activity)
                .filter(Activity.is_active == True, Activity.event_date > now)
                .all()
            )

            for activity in activities:
                time_until = (activity.event_date - now).total_seconds() / 60

                # Envoyer les rappels
                for reminder_min in activity.reminders:
                    if abs(time_until - reminder_min) < 1:
                        await self.send_reminder(activity, reminder_min)

                # Démarrer l'activité si c'est l'heure
                if time_until <= 0:
                    await self.start_activity(activity, session)
        finally:
            session.close()

    async def send_reminder(self, activity, minutes):
        """Envoyer un rappel dans le thread"""
        thread = self.bot.get_channel(int(activity.thread_id))
        if not thread:
            return

        # Récupérer le rôle via l'ID
        role = (
            thread.guild.get_role(int(activity.ping_role_id))
            if activity.ping_role_id
            else None
        )

        if role:
            if role.name == "@everyone" or role.name == "@here":
                mention = f"{role.name}"
            else:
                mention = role.mention
        else:
            mention = ""

        await thread.send(
            f"⏰ {mention} **Rappel !** L'activité **{activity.title}** commence dans **{minutes} minutes** !"
        )

    async def start_activity(self, activity, session):
        """Démarrer l'activité"""
        thread = self.bot.get_channel(int(activity.thread_id))
        if not thread:
            return

        role = (
            thread.guild.get_role(int(activity.ping_role_id))
            if activity.ping_role_id
            else None
        )
        if role:
            mention = (
                role.mention if role.name not in ["@everyone", "@here"] else role.name
            )
        else:
            mention = ""

        registrations = (
            session.query(Registration).filter_by(activity_id=activity.id).all()
        )

        await thread.send(
            f"🚨 {mention} **MASS UP !**\n\n"
            f"L'activité **{activity.title}** commence maintenant !\n"
            f"👥 **{len(registrations)} joueurs inscrits**\n"
            f"👑 Leader : <@{activity.leader}>"
        )

        activity.is_active = False
        session.commit()


async def setup(bot):
    cog = ActivityCog(bot)
    await bot.add_cog(cog)
