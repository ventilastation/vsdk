def generate_semitones():
    """
    Generate a list of semitone frequencies for one octave.
    The first element is the frequency of C4 (Middle C).
    """
    c4 = 261.6255653006  # Frequency of Middle C (C4)
    semitones = [c4 * (2 ** (i / 12)) for i in range(-60, 128-60)]
    return semitones

def main():
    semitones = generate_semitones()
    for i, freq in enumerate(semitones):
        print(f"Semitone {i}: {freq:.3f} Hz")

if __name__ == "__main__":
    main()

# This code generates the frequencies of the 12 semitones in one octave starting from Middle C (C4).
# Each semitone is calculated using the formula: frequency = C4 * (2 ** (i / 12)), where i is the index of the semitone.
