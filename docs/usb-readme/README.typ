// MeccanicOS-README.pdf: the instructions next to MeccanicOS on the USB drive (the root
// of the ISO, and of Ventoy sticks: mos-usb, ./start ventoy). Built by
// flake.nix (packages.readme-pdf) with the logo, as the desktop's top bar shows
// it (branding/logo/meccanicos-logo-black.svg, from branding/logos.py), as
// logo.svg.
#let amber = rgb("#f8a800")
#let teal = rgb("#288080")
#let graphite = rgb("#2b2b2b")
#let dim = rgb("#6b6b6b")

#set document(title: "MeccanicOS: start here", author: "MeccanicOS")
#set page(
  paper: "a4",
  margin: (x: 2cm, top: 1.5cm, bottom: 1.8cm),
  footer: context [
    #set text(8.5pt, fill: dim)
    #link("https://meccanicos.com")[meccanicos.com] #h(1fr)
    Support: #link("https://groups.google.com/g/meccanicos")[groups.google.com/g/meccanicos] #h(1fr)
    #counter(page).display("1 / 1", both: true)
  ],
)
#set text(font: "Inter", size: 10pt, fill: graphite, lang: "en", hyphenate: false)
#set par(justify: true, leading: 0.62em, spacing: 0.9em)
#show table: set par(justify: false)
#show link: set text(fill: teal)
#show heading: set text(fill: graphite)
#show heading.where(level: 1): it => {
  v(0.6em)
  block(below: 0.5em, text(14pt, weight: "bold", it.body))
  line(length: 2.2cm, stroke: 2pt + amber)
  v(0.2em)
}
#show heading.where(level: 2): it => block(above: 1.1em, below: 0.6em, text(11.5pt, weight: "bold", it.body))
#show raw: set text(font: "JetBrains Mono", size: 9.5pt)
#let key(k) = box(
  inset: (x: 4pt, y: 1.5pt), outset: (y: 1.5pt), radius: 3pt,
  stroke: 0.6pt + dim, fill: luma(246),
  text(font: "JetBrains Mono", size: 9pt, weight: "bold", k),
)
#let note(body) = block(
  width: 100%, inset: (x: 12pt, y: 9pt), radius: 4pt,
  fill: rgb("#fff6e0"), stroke: (left: 3pt + amber), body,
)

#align(center, image("logo.svg", width: 9cm))
#v(0.6em)

Thank you for trying MeccanicOS! This USB drive contains an ISO file: it is a
complete operating system. You can start your computer from it and use it
*without deleting files on your computer*. You can also keep your home folder,
encrypted, on the same USB drive: then the drive is a complete computer you can
carry in your pocket. You can also install MeccanicOS on the computer, but if you
do, *the computer's current operating system and all the files on it are deleted*.
Before you install, make a copy of your files on another drive.

= Start your computer from the USB drive

When a computer starts, it first loads its main program: the _operating system_
(for example Windows). Usually it loads it from its own disk. You can tell it to
load it from the USB drive instead, so that it starts MeccanicOS and not its usual
system. This is called _booting_ from the USB drive.

Starting from the USB drive is safe (unless you choose to install MeccanicOS). To go
back to the computer's usual system, shut down and unplug the drive.

+ *Plug in* the USB drive. If you can, plug it into the computer itself, not into a hub.
+ *Turn on the computer* (or restart it). *Right away, press the boot menu key*
  (from the table at the end) again and again, about twice a second, until you see
  a list of devices. The key is often shown on the screen for a moment when the
  computer starts.
+ *Choose the USB drive.* If it is in the list twice, choose the one that starts
  with *UEFI*.
+ If you see a menu called *Ventoy*, choose the file whose name starts with
  `meccanicos`, then choose *Boot in normal mode*.
+ In the MeccanicOS menu, choose *MeccanicOS*. If the screen stays black, restart
  and choose the line that ends with *nomodeset*.

After a minute or two, you see the MeccanicOS desktop. To start anything, press
#key[Super]+#key[Space] (the Windows key and the space bar together) and type what
you want. Type *Help* to read the manual.

== From Windows, without the keys

Plug in the USB drive. In Windows, open *Settings → System → Recovery*. Next to
*Advanced startup*, click *Restart now*. Then choose *Use a device* and choose the
USB drive. (Another way: hold the #key[Shift] key while you click *Restart* in the
Start menu.)

= If it does not start

Most computers start from the USB drive as described above. If the computer starts
Windows anyway, does not show the USB drive, or shows an error like _Secure Boot
violation_, some settings may need to change. They are in the computer's _setup_
(often called the _BIOS_).

#note[
  *Be careful.* Changing these settings is your own choice and your own
  responsibility. Before you change anything:
  - *Write down* each setting and its old value, so you can put it back.
  - If Windows is on the computer, have your *BitLocker recovery key* ready
    (#link("https://aka.ms/myrecoverykey")[aka.ms/myrecoverykey], if you sign in to Windows
    with a Microsoft account). After some changes, Windows asks for it when it starts.
  - If you are not sure, *do not change it*. Ask someone who knows computers, or ask
    in the group (see Support below).
]

To open the setup, turn on the computer and right away press the setup key from
the table at the end, again and again. From Windows: hold #key[Shift] while you click *Restart*,
then choose *Troubleshoot → Advanced options → UEFI Firmware Settings*. Move around
with the arrow keys. The settings are usually under *Boot*, *Security* or *Advanced*.
When you are done, choose *Save and Exit* (often the #key[F10] key). Change one
thing at a time, then try again.

- *Secure Boot: turn it off.* This is the most common reason a computer does not
  start MeccanicOS. On some computers you must first set a password in the setup
  before you can change Secure Boot. If you set one, *write it down*: without it,
  you may not be able to change the settings again.
- *Fast Boot: turn it off.* When it is on, the computer may ignore the boot menu key.
- *USB boot: turn it on*, if your setup has it (it may be called _USB Boot_, _Boot from
  USB_ or _External Device Boot_). On Acer computers, also turn on _F12 Boot Menu_.
- *Boot order:* if no boot menu key works, move the USB drive to the top of the
  _boot order_. Put the old order back when you are done.

To go back, open the setup again, put back the values you wrote down, and choose
*Save and Exit*.

== Still not working?

- Try *another USB port*. Use a port on the computer itself.
- *Black screen* after you choose MeccanicOS: restart and choose the line that ends
  with *nomodeset*.
- *The USB drive is not in the list:* make the USB drive again, or try another USB
  drive. Some USB drives are slow or broken.
- *You want to install, but MeccanicOS does not see the computer's disk:* do not
  change more settings. Ask in the group first.

= Learn more

#link("https://meccanicos.com")[*meccanicos.com*] has videos, pictures of every tool,
how to make another USB drive, and the full manual. In MeccanicOS, the manual is also
in *Help* (press #key[Super]+#key[Space] and type _Help_).

= License

MeccanicOS is free and open source software. Its own files are under the
BSD 3-Clause License:
#link("https://github.com/unofficialtools/meccanicos/blob/main/LICENSE")[github.com/unofficialtools/meccanicos/blob/main/LICENSE].
The other programs on this USB drive have their own licenses (GPL, MIT, BSD, Apache,
MPL and others). All of them allow you to copy this USB drive and give it to others.
Source code: #link("https://github.com/unofficialtools/meccanicos")[github.com/unofficialtools/meccanicos].

*No warranty.* MeccanicOS is provided "as is", without any warranty. You use it,
and change your computer's settings, at your own risk. The authors are not
responsible for any damage or loss of data.

= Support

There is no official support: MeccanicOS is free and open source software. You can
ask questions, and read questions others asked before, in the MeccanicOS group:
#align(center, block(above: 0.8em, below: 0.8em,
  link("https://groups.google.com/g/meccanicos", text(12pt, weight: "bold")[groups.google.com/g/meccanicos])))
The people there are volunteers who help in their free time, so please be kind to them.

When you ask, say which computer you have (maker and model) and what you see on the
screen. A photo of the screen helps.

#pagebreak()

= Boot menu and setup keys

#table(
  columns: (1.3fr, 1fr, 1fr),
  stroke: (x, y) => if y == 0 { (bottom: 1pt + graphite) } else { (bottom: 0.4pt + luma(220)) },
  inset: (x: 6pt, y: 5pt),
  table.header([*Computer maker*], [*Boot menu key*], [*Setup (BIOS) key*]),
  [Dell], [#key[F12]], [#key[F2]],
  [HP], [#key[F9] (or #key[Esc], then #key[F9])], [#key[F10]],
  [Lenovo], [#key[F12] (some: the small Novo button)], [#key[F1] or #key[F2]],
  [Acer], [#key[F12] (may need to be turned on in setup)], [#key[F2] or #key[Del]],
  [ASUS], [#key[Esc] (laptops), #key[F8] (desktops)], [#key[F2] or #key[Del]],
  [MSI], [#key[F11]], [#key[Del]],
  [Gigabyte, Toshiba, Dynabook], [#key[F12]], [#key[F2] or #key[Del]],
  [ASRock], [#key[F11]], [#key[F2] or #key[Del]],
  [Samsung], [#key[Esc] or #key[F2]], [#key[F2]],
  [Microsoft Surface], [hold Volume Down, press Power], [hold Volume Up, press Power],
  [Intel NUC], [#key[F10]], [#key[F2]],
  [Mac with an Intel processor], [hold #key[Option] (⌥) when you turn it on, then choose _EFI Boot_], [—],
)
#text(9pt, fill: dim)[These are the usual keys; your computer may use a different one. Macs
with Apple processors (M1 and newer) cannot start MeccanicOS: it works only on computers
with Intel or AMD processors.]
