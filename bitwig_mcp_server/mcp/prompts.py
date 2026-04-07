"""
Bitwig MCP Prompts

MCP prompt template implementations for Bitwig Studio integration.
"""

from typing import Optional

from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent, Role


class BitwigPrompts:
    """Helper for Bitwig-specific MCP prompt templates"""

    @staticmethod
    def list_prompts() -> list[Prompt]:
        """Get a list of all available Bitwig prompts"""
        return [
            Prompt(
                name="setup_mixing_session",
                description="Set up a new mixing session with default settings",
                arguments=[
                    PromptArgument(
                        name="num_tracks",
                        description="Number of tracks to create",
                        required=False,
                    )
                ],
            ),
            Prompt(
                name="create_track_template",
                description="Create a track template with specific devices and settings",
                arguments=[
                    PromptArgument(
                        name="track_type",
                        description="Type of track (e.g., drums, bass, vocals)",
                        required=True,
                    ),
                    PromptArgument(
                        name="genre",
                        description="Musical genre for optimizing presets",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="optimize_track_settings",
                description="Get recommendations for optimizing track settings",
                arguments=[
                    PromptArgument(
                        name="track_type",
                        description="Type of track (e.g., drums, bass, vocals)",
                        required=True,
                    ),
                    PromptArgument(
                        name="problem",
                        description="Specific problem to address (e.g., muddy, harsh, thin)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="start_creating_music",
                description=(
                    "Workflow to start making music in Bitwig via MCP (tracks, devices, clips, MIDI)"
                ),
                arguments=[
                    PromptArgument(
                        name="style",
                        description="Optional genre or vibe (e.g. minimal techno, hip hop)",
                        required=False,
                    )
                ],
            ),
        ]

    @staticmethod
    def get_prompt(
        name: str, arguments: Optional[dict[str, str]] = None
    ) -> list[PromptMessage]:
        """Get a specific prompt template with arguments filled in"""
        if arguments is None:
            arguments = {}

        if name == "setup_mixing_session":
            num_tracks = arguments.get("num_tracks", "8")
            return [
                PromptMessage(
                    role=Role.USER,
                    content=TextContent(
                        type="text",
                        text=f"""I want to set up a new mixing session in Bitwig Studio.

Here's what I need help with:
1. Creating a balanced mix template with {num_tracks} tracks
2. Setting up appropriate sends for reverb and delay
3. Configuring monitor output and gain staging
4. Setting up basic mastering chain on the master track

Can you help me set this up step by step?""",
                    ),
                )
            ]

        elif name == "create_track_template":
            track_type = arguments.get("track_type", "")
            genre = arguments.get("genre", "general")

            return [
                PromptMessage(
                    role=Role.USER,
                    content=TextContent(
                        type="text",
                        text=f"""I need to create a template for a {track_type} track in Bitwig Studio for {genre} music.

Please help me with:
1. What devices should I add to this track type?
2. What settings and parameters would work well for this type of track?
3. How should I set up the routing and monitoring?
4. Are there any specific EQ or compression settings that would work well?

Can you provide detailed step-by-step guidance?""",
                    ),
                )
            ]

        elif name == "optimize_track_settings":
            track_type = arguments.get("track_type", "")
            problem = arguments.get("problem", "general balance")

            return [
                PromptMessage(
                    role=Role.USER,
                    content=TextContent(
                        type="text",
                        text=f"""I'm having issues with my {track_type} track in Bitwig Studio. The specific problem is that it sounds {problem}.

Can you help me:
1. Identify common causes for this issue with this type of track
2. Suggest parameter adjustments for EQ, compression, and other processing
3. Recommend specific Bitwig devices and settings to address the problem
4. Propose a step-by-step approach to fix the issue

Please give me detailed settings I can try.""",
                    ),
                )
            ]

        elif name == "start_creating_music":
            style = arguments.get("style", "your chosen style")
            return [
                PromptMessage(
                    role=Role.USER,
                    content=TextContent(
                        type="text",
                        text=f"""I want to start making music in Bitwig Studio using the Bitwig MCP tools and the Open Sound Controller (DrivenByMoss) OSC extension.

Target vibe: {style}.

Please drive Bitwig with the MCP tools in a sensible order:

1. set_layout to arrange when working on timeline/launcher; use mix for levels.
2. set_tempo for BPM.
3. add_instrument_track (and add_audio_track if needed). select_track on the bank index I care about; use navigate_track_bank if tracks are off the current OSC bank page.
4. set_track_name for Kick, Bass, etc.
5. browse_insert_device or device_browser_workflow to load built-in instruments (after selecting the first device slot on that track in Bitwig if needed).
6. Clips: insert_seed_midi_clip for built-in MIDI (bars=8 for 8-bar clips; drums_all_in_one_gm_8bar needs Drum Machine on that track). Long chord stacks in seeds (organ_plenum, pad, fugue_organ) sound organ-like on any sustained synth; use different devices per role (bass vs chords vs lead). Many 8-bar seeds now send CC1 (mod wheel) and CC11 (expression); map those on the instrument for motion. LAUNCHER vs TIMELINE: launcher_clip_* is the scene grid; arranger uses clip_create_at_cursor or record. send_midi_note / play_midi_note_sequence; clip_quantize_selected when done.
7. Mix: song_enhance_mix, set_track_send, set_project_remote_control (map remotes in Bitwig first); set_track_mute_state / solo; set_device_parameter; open_track_device_browser for Polymer, Polysynth, Sampler, Drum Machine, Organ only where appropriate.

Remind me: OSC track and clip indices are bank-relative (often 1-8 unless I increased bank page size in Bitwig). Virtual MIDI requires the MIDI input port configured in the OSC extension.

Build a minimal first idea (a few tracks, one clip pattern, basic levels) using these tools.""",
                    ),
                )
            ]

        else:
            raise ValueError(f"Unknown prompt: {name}")
