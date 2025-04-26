from pydub import AudioSegment, silence


def remove_silence_everywhere(file_path: str, silence_thresh: float = -40.0, min_silence_len: int = 1000, keep_silence_ms: int = 500):
    print(f"Removing silence inside {file_path}")
    file_format = file_path.split(".")[-1]
    sound = AudioSegment.from_file(file_path, format=file_format)

    chunks = silence.split_on_silence(
        sound,
        min_silence_len=min_silence_len,     # only cut silences longer than 500ms
        silence_thresh=silence_thresh,       # treat anything below -35dBFS as silence
        keep_silence=keep_silence_ms         # leave 200ms of silence at each cut
    )

    if not chunks:
        print("No sound detected above silence threshold. Skipping.")
        return

    combined = AudioSegment.empty()
    for chunk in chunks:
        combined += chunk

    combined.export(file_path, format=file_format)
    print(f"Silence removed inside and saved to {file_path}")

if __name__ == "__main__":
    file_path = r"CURRENTLY_RECORDING\Test - Pineland - April 25 Friday 2025 09_14 PM - 0m 19s.mp3"
    remove_silence_everywhere(file_path)