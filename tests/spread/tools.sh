tools.setup_snapd_proxy() {
  if [ "${SNAPD_USE_PROXY:-}" != true ]; then
    return
  fi

  local SNAPD_CONFD="/etc/systemd/system/snapd.service.d"
  mkdir -p "$SNAPD_CONFD"

  cat <<EOF >${SNAPD_CONFD}/proxy.conf
[Service]
Environment=HTTPS_PROXY="$HTTPS_PROXY" HTTP_PROXY="$HTTPS_PROXY" https_proxy="$HTTPS_PROXY" http_proxy="$HTTPS_PROXY" NO_PROXY="$NO_PROXY" no_proxy="$NO_PROXY"
EOF

  # Since the service config changed, restart
  systemctl daemon-reload
  systemctl restart snapd.service
}

tools.mount_image() {
  local img_path="$1"

  local tmp_dir
  tmp_dir=$(mktemp -d)
  local mount_root="${tmp_dir}/mount"
  mkdir -p "${mount_root}"

  echo "${mount_root}" >tmpmount.txt
  echo "${tmp_dir}" >tmpdir.txt

  local loop_dev
  loop_dev=$(losetup --find --show --partscan "${img_path}")
  echo "${loop_dev}" >loop.txt

  # Partition devices are created asynchronously by the kernel after the
  # partscan ioctl; wait for them to appear before using them.
  local count=0
  until ls -d "${loop_dev}"p* >/dev/null 2>&1; do
    count=$((count + 1))
    if [ "${count}" -ge 100 ]; then
      echo "Timed out waiting for ${loop_dev} partition devices" >&2
      losetup -d "${loop_dev}" || true
      return 1
    fi
    sleep 0.1
  done

  # Use nullglob to avoid a literal string if no partitions were found
  local saved_nullglob
  saved_nullglob=$(shopt -p nullglob || true)
  shopt -s nullglob
  for part in ${loop_dev}p*; do
    local p_name=${part#${loop_dev}}
    mkdir -p "${mount_root}/${p_name}"
    mount "${part}" "${mount_root}/${p_name}" || true
  done
  shopt -u nullglob
  eval "$saved_nullglob"

  echo "${mount_root}"
}

tools.check_metadata() {
  local metadata_file="$1"

  test -f "${metadata_file}"
  # -e makes yq exit non-zero if the file doesn't parse or the field is absent.
  # Feed the file through stdin to avoid problems with strict snap restrictions.
  yq -e '.name | length > 0' <"${metadata_file}"
}

tools.check_partition_metadata() {
  local mount_root="$1"
  local partition_name="$2"

  tools.check_metadata "${mount_root}/${partition_name}/.image/metadata.yaml"
}

tools.umount_image() {
  if [ -f loop.txt -a -f tmpmount.txt ]; then
    local loop_dev
    loop_dev=$(cat loop.txt)
    local mount_root
    mount_root=$(cat tmpmount.txt)

    # Use nullglob to avoid a literal string if no partitions were found
    local saved_nullglob
    saved_nullglob=$(shopt -p nullglob || true)
    shopt -s nullglob
    for part in ${loop_dev}p*; do
      local p_name=${part#${loop_dev}}
      mount --make-rprivate "${mount_root}/${p_name}" || true
      # Unmount fully so the loop device can be detached; fall back to a lazy
      # unmount, which leaves the mount pending and can keep the device busy.
      umount --recursive "${mount_root}/${p_name}" || umount -l "${mount_root}/${p_name}" || true
    done
    shopt -u nullglob
    eval "$saved_nullglob"

    losetup -d "${loop_dev}" || true
    sync
    . /etc/os-release
    if [[ "${VERSION_CODENAME}" == "jammy" ]]; then
      # On Jammy, it takes a tick or two after sync for the device to actually
      # get removed. Sleeping for a second and syncing is more than enough time
      # to work around it.
      sleep 1
      sync
    fi
    losetup -l | NOMATCH "${loop_dev}"
    rm -f loop.txt
  fi

  rm -f tmpmount.txt

  if [ -f tmpdir.txt ]; then
    rm -rf "$(cat tmpdir.txt)"
    rm tmpdir.txt
  fi
}
